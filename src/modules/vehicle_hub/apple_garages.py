"""Apple Maps directory. Place IDs are stored separately from service consent."""
import math
import os
import threading
import time
from urllib.parse import urlencode
import jwt
import requests
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String, ForeignKey
from .database import Base


class HomeGarage(Base):
    __tablename__ = 'customer_home_garages'
    customer_id = Column(Integer, ForeignKey('customers.id'), primary_key=True)
    apple_place_id = Column(String(128), nullable=False)


_lock = threading.Lock()
_token = None
_token_until = 0


def configured():
    return all(os.environ.get(key, '').strip() for key in ('APPLE_MAPS_TEAM_ID', 'APPLE_MAPS_KEY_ID', 'APPLE_MAPS_PRIVATE_KEY'))


def _maps_token():
    global _token, _token_until
    if not configured():
        raise HTTPException(503, 'Katalog Apple Map zatím není připojený. Registrované servisy zůstávají dostupné.')
    with _lock:
        if _token and time.time() < _token_until:
            return _token
        now = int(time.time())
        try:
            signed = jwt.encode({'iss': os.environ['APPLE_MAPS_TEAM_ID'], 'iat': now,
                'exp': now + 300, 'scope': 'server_api'}, os.environ['APPLE_MAPS_PRIVATE_KEY'].replace('\\n', '\n'),
                algorithm='ES256', headers={'kid': os.environ['APPLE_MAPS_KEY_ID'], 'typ': 'JWT'})
            response = requests.get('https://maps-api.apple.com/v1/token',
                headers={'Authorization': 'Bearer ' + signed}, timeout=8)
            response.raise_for_status()
            data = response.json()
            _token = data['accessToken']
            _token_until = now + min(int(data['expiresInSeconds']), 1800) - 60
            return _token
        except (requests.RequestException, ValueError, KeyError, jwt.PyJWTError):
            raise HTTPException(503, 'Katalog Apple Map není nyní dostupný. Zkuste hledání později.') from None


def _get(path, params):
    try:
        response = requests.get('https://maps-api.apple.com/v1/' + path,
            params={**params, 'lang': 'cs-CZ'}, headers={'Authorization': 'Bearer ' + _maps_token()}, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(503, 'Vyhledávání v Apple Mapách se nezdařilo. Zkuste to znovu.') from None


def place_row(place, center=None):
    point = place.get('coordinate') or {}
    lat, lon = float(point['latitude']), float(point['longitude'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid place coordinate')
    row = {'id': place.get('id'), 'name': place.get('name') or 'Autoservis',
        'address': ', '.join(place.get('formattedAddressLines') or []),
        'latitude': lat, 'longitude': lon, 'source': 'Apple Maps', 'registered': False,
        'map_url': 'https://maps.apple.com/?' + urlencode({'q': place.get('name') or 'Autoservis', 'll': f'{lat},{lon}'}),
        'navigation_url': 'https://maps.apple.com/?' + urlencode({'daddr': f'{lat},{lon}', 'dirflg': 'd'})}
    if center:
        a,b = map(math.radians, center); c,d = map(math.radians, (lat,lon))
        hav = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
        row['distance_km'] = round(6371 * 2 * math.asin(math.sqrt(min(1,max(0,hav)))), 1)
    return row


def search(city, query='autoservis'):
    towns = _get('search', {'q': city, 'limitToCountries': 'CZ', 'resultTypeFilter': 'Address'}).get('results') or []
    if not towns:
        raise HTTPException(404, 'Město nebylo nalezeno. Doplňte okres nebo PSČ.')
    try: center = place_row(towns[0])
    except (KeyError,TypeError,ValueError):
        raise HTTPException(503, 'Polohu města se nepodařilo načíst. Zkuste hledání znovu.') from None
    lat,lon=center['latitude'],center['longitude']
    dy = 20/111.32; dx=20/(111.32*max(.1, math.cos(math.radians(lat))))
    response = _get('search', {'q': query or 'autoservis', 'includePoiCategories': 'AutomotiveRepair',
        'resultTypeFilter':'Poi', 'searchLocation':f'{lat},{lon}',
        'searchRegion':f'{lat+dy},{lon+dx},{lat-dy},{lon-dx}', 'searchRegionPriority':'required'})
    rows=[];seen=set()
    for place in response.get('results') or []:
        try: row=place_row(place,(lat,lon))
        except (KeyError,TypeError,ValueError): continue
        key=row['id'] or (row['name'],row['latitude'],row['longitude'])
        if key in seen: continue
        seen.add(key); rows.append(row)
    return {'source':'Apple Maps', 'reference':center, 'items':sorted(rows,key=lambda r:r['distance_km']),
        'notice':'Výsledky z Apple Map zahrnují i servisy bez účtu v Evidenci Vozidel. Vzdálenost je vzdušnou čarou od vybraného města.'}


def detail(place_id):
    data=_get('place', {'ids':place_id})
    items=data.get('results') or []
    if not items: raise HTTPException(404,'Servis již v mapách není dostupný. Vyhledejte jej znovu.')
    try: return place_row(items[0])
    except (KeyError,TypeError,ValueError): raise HTTPException(503,'Údaje servisu se nepodařilo načíst.') from None
