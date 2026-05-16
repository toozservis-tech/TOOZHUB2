from __future__ import annotations

from types import SimpleNamespace

from src.modules.vehicle_hub.services.vehicle_technical_overview import (
    OVERVIEW_VERSION,
    build_vehicle_technical_overview,
    build_technical_overview_debug_payload,
    flatten_key_paths,
    pick_value,
    pick_value_detailed,
    technical_overview_for_api,
)


def test_pick_value_priority_mdcr_over_vehicle() -> None:
    sources = {
        "mdcr": {"TovarniZnacka": "ŠKODA"},
        "local_vin": {"make": "LocalMake"},
        "vehicle": {"brand": "VehicleBrand"},
    }
    val, src = pick_value(sources, ("TovarniZnacka", "make", "brand"))
    assert val == "ŠKODA"
    assert src == "mdcr"


def test_pick_value_nested_dotted_path() -> None:
    sources = {"mdcr": {"technickeUdaje": {"motor": {"vykon_kw": 77}}}}
    val, src = pick_value(sources, ("technickeUdaje.motor.vykon_kw",))
    assert val == "77"
    assert src == "mdcr"


def test_pick_value_case_insensitive_key() -> None:
    sources = {"mdcr": {"tovarniznacka": "VW"}}
    val, src = pick_value(sources, ("TovarniZnacka",))
    assert val == "VW"


def test_pick_value_ascii_fold_diacritics() -> None:
    sources = {"mdcr": {"PřílišKlíc": "ANO"}}
    val, src = pick_value(sources, ("PrilisKlic",))
    assert val == "ANO"


def test_pick_value_traverses_list_index() -> None:
    sources = {"mdcr": {"polozky": [{"barva": "Červená"}]}}
    val, src = pick_value(sources, ("polozky[0].barva",))
    assert "erven" in val or val == "Červená"


def test_pick_value_preserves_zero_and_ne() -> None:
    v, _, st, _ = pick_value_detailed({"mdcr": {"x": 0}}, ("x",))
    assert v == "0" and st == "filled"
    v2, _, st2, _ = pick_value_detailed({"mdcr": {"x": "NE"}}, ("x",))
    assert v2 == "NE" and st2 == "filled"


def test_flatten_key_paths_nested() -> None:
    data = {"a": {"b": {"c": 1}}, "d": [{"e": 2}]}
    paths = flatten_key_paths(data)
    assert "a.b.c" in paths
    assert any(p.startswith("d[0]") for p in paths)


def test_technical_overview_fourteen_sections_and_fixed_labels() -> None:
    vin = "WVGZZZ1TZ9W053855"
    vehicle = SimpleNamespace(
        vin=vin,
        brand="VW",
        model="Tiguan",
        year=2009,
        engine="2.0 TDI",
        plate="1A2 3456",
        fuel="Nafta",
        body_type="SUV",
        tyres_info="205/55 R16",
    )
    mdcr = {
        "TovarniZnacka": "Volkswagen",
        "ObchodniOznaceni": "Tiguan",
        "MotorMaxVykon": "103 / 3800",
        "MotorOtackyPriMaxVykonu": "4000",
        "NapravyPneuRafky": "N.1: 205/55 R16",
    }
    out = build_vehicle_technical_overview(vehicle, mdcr_raw=mdcr, local_decoded=None)
    assert out["version"] == OVERVIEW_VERSION
    assert len(out["sections"]) == 14
    titles = [s["title"] for s in out["sections"]]
    assert titles[0] == "Vozidlo"
    assert titles[1] == "Motor"
    assert titles[-1] == "Další záznamy"
    assert out["stats"]["total"] >= 90
    assert out["stats"]["filled"] > 0
    vehicle_sec = out["sections"][0]["rows"]
    labels_v = [r["label"] for r in vehicle_sec]
    assert labels_v[0] == "ZTP"
    assert "VIN" in labels_v
    pub = technical_overview_for_api(out)
    assert pub is not None
    assert "raw" not in pub
    assert "sections" in pub
    row0 = pub["sections"][0]["rows"][0]
    assert "candidate_keys" not in row0
    assert "matched_key" not in row0


def test_technical_overview_missing_values_are_null() -> None:
    vehicle = SimpleNamespace(
        vin="TMBABCDEFGHJKLMNO",
        brand=None,
        model=None,
        year=None,
        engine=None,
        plate=None,
        fuel=None,
        body_type=None,
        tyres_info=None,
    )
    out = build_vehicle_technical_overview(vehicle, mdcr_raw={}, local_decoded=None)
    first_row = out["sections"][0]["rows"][0]
    assert first_row["value"] is None
    assert first_row["status"] == "source_not_available"


def test_technical_overview_stats_by_section() -> None:
    vin = "WVGZZZ1TZ9W053855"
    vehicle = SimpleNamespace(
        vin=vin,
        brand="VW",
        model="Tiguan",
        year=2009,
        engine="",
        plate="",
        fuel="",
        body_type="",
        tyres_info="",
    )
    out = build_vehicle_technical_overview(vehicle, mdcr_raw={"TovarniZnacka": "VW"}, local_decoded=None)
    bs = out["stats"]["by_section"]
    assert isinstance(bs, dict)
    assert bs["Vozidlo"]["total"] >= 1


def test_build_technical_overview_debug_payload_structure() -> None:
    vin = "WAUZZZ8K29A010069"
    ov = build_vehicle_technical_overview(
        SimpleNamespace(
            vin=vin,
            brand=None,
            model=None,
            year=None,
            engine=None,
            plate=None,
            fuel=None,
            body_type=None,
            tyres_info=None,
        ),
        mdcr_raw={"TovarniZnacka": "Audi", "MotorTyp": "TDI"},
        local_decoded=None,
    )
    dbg = build_technical_overview_debug_payload(
        vin=vin,
        overview_stored=ov,
        mdcr_raw={"TovarniZnacka": "Audi", "MotorTyp": "TDI"},
    )
    assert dbg["vin"] == vin
    assert "MotorTyp" in dbg["mdcr_top_level_keys"] and "TovarniZnacka" in dbg["mdcr_top_level_keys"]
    assert "candidate_key_misses" in dbg


def test_yv1_volvo_datova_kostka_fixture_mapping() -> None:
    """Regrese: YV1MW753152118404 — Datová kostka / MDČR aliasy (fixture ≠ vždy API klíče)."""
    vin = "YV1MW753152118404"
    fixture = {
        "DatumPrvniRegistrace": "2005-08-31T00:00:00",
        "DatumPrvniRegistraceVCr": "2019-11-21T00:00:00",
        "EsEu": "e4*2001/116*0076*05",
        "DruhVozidla": "OSOBNÍ AUTOMOBIL",
        "DruhVozidlaRadek2": "AC KOMBI",
        "KategorieVozidla": "M1",
        "TovarniZnacka": "VOLVO",
        "Typ": "/ M",
        "Varianta": "MW75",
        "Verze": "MW7531",
        "Vin": vin,
        "ObchodniOznaceni": "V50 2.0D",
        "VyrobceVozidla": "VOLVO CAR CORP., GOTHENBURG, ŠVÉDSKO",
        "VyrobceMotoru": "VOLVO CAR CORP., GOTHENBURG, ŠVÉDSKO",
        "TypMotoru": "D4204T",
        "MaxVykonKw": 100,
        "MaxVykonOtacky": 4000,
        "Palivo": "NM",
        "ZdvihovyObjem": 1997,
        "PlneElektrickeVozidlo": "NE",
        "HybridniVozidlo": "NE",
        "EmisniLimit": "/ 2003/76A",
        "KorigovanySoucinitelAbsorbce": "1.33",
        "Co2Mesto": 203,
        "Co2MimoMesto": 123,
        "Co2Kombinovane": 153,
        "SpotrebaPredpis": "ES 1999/100",
        "SpotrebaMesto": "7.6",
        "SpotrebaMimoMesto": "4.6",
        "SpotrebaKombinovana": "5.7",
        "Barva": "ČERNÁ",
        "PocetMistCelkem": 5,
        "PocetMistKSezeni": 5,
        "PocetMistKStani": "",
        "Delka": 4514,
        "Sirka": 1770,
        "Vyska": 1452,
        "Rozvor": "2 640",
        "Rozchod": "1550/ 1540/ /",
        "ProvozniHmotnost": 1470,
        "HmotnostiTechnickyPripustna": 1960,
        "HmotnostiPovolena": 1960,
        "HmotnostiPripojneBrzdeneTechnickyPripustna": 1500,
        "HmotnostiPripojneBrzdenePovolena": 1500,
        "HmotnostiPripojneNebrzdeneTechnickyPripustna": 700,
        "HmotnostiPripojneNebrzdenePovolena": 700,
        "HmotnostiSoupravyTechnickyPripustna": 3460,
        "HmotnostiSoupravyPovolena": 3460,
        "HmotnostiZatizeniSz": 75,
        "HmotnostiZatizeniSzTyp": "Z",
        "PocetNaprav": 2,
        "PohaneneNapravy": "- 1 PŘEDNÍ",
        "KolaPneumatiky": "195/60 R 16 90V/ 6.5 J X 16 ET52.5; ...",
        "HlukStojici": 78,
        "HlukStojiciOtacky": 3000,
        "HlukJizda": 73,
        "NejvyssiRychlost": 210,
        "Ucel": "Běžný provoz",
        "CisloTp": "UK056154",
        "CisloOrv": "UAX775472",
        "ZadrzenoOrv": "NE",
        "DruhRz": "STD. SILNIČNÍ",
        "VariantaRz": 101,
        "ZadrzenaRzPosledni": "NE",
        "ZarazeniVozidla": "RSV",
        "TechnickaProhlidkaDo": "2028-04-09T00:00:00",
        "TechnickaProhlidkaPredRegistraci": "2019-10-23T00:00:00",
        "Status": "PROVOZOVANÉ",
        "PocetVlastniku": 1,
        "PocetProvozovatelu": 1,
        "AutonomniStupen": "Neuvedeno",
        "DalsiZaznamy": (
            "Rozchod: 1 550/1 540.\nVariabilní provedení vozidla:\n"
            "*14: je-li vozidlo vybaveno integrovaným podélným střešním nosičem zavazadel"
        ),
    }
    vehicle = SimpleNamespace(
        vin=vin,
        brand=None,
        model=None,
        year=None,
        engine=None,
        plate=None,
        fuel=None,
        body_type=None,
        tyres_info=None,
    )
    out = build_vehicle_technical_overview(vehicle, mdcr_raw=fixture, local_decoded=None)
    rows = {r["label"]: r["value"] for sec in out["sections"] for r in sec["rows"]}

    assert rows["Druh vozidla"] == "OSOBNÍ AUTOMOBIL"
    assert rows["Typ"] == "/ M"
    assert rows["ES/EU"] == "e4*2001/116*0076*05"
    assert "VOLVO" in str(rows.get("Výrobce vozidla"))
    assert "VOLVO" in str(rows.get("Výrobce motoru"))
    assert rows["CO2 město/mimo město/kombinované [g.km-1]"] == "203 / 123 / 153"
    assert rows["Spotřeba město/mimo město/kombinovaná [l.100km⁻¹]"] == "7.6 / 4.6 / 5.7"
    assert rows["Barva"] == "ČERNÁ"
    assert rows["Celková délka/šířka/výška [mm]"] == "4514/ 1770/ 1452"
    assert rows["Provozní hmotnost"] == "1470"
    assert rows["Největší technicky přípustná/povolená hmotnost přípojného vozidla [kg] brzděného"] == "1500 / 1500"
    assert rows["Za jízdy"] == "73"
    assert rows["Status"] == "PROVOZOVANÉ"
    assert rows["Datum 1. registrace"] == "31.08.2005"
    assert rows["Pravidelná technická prohlídka do"] == "09.04.2028"
    assert rows["Autonomní Stupeň"] == "Neuvedeno"
    assert rows["Další záznamy"] and len(str(rows["Další záznamy"])) > 40
    assert rows["Plně elektrické vozidlo"] == "NE"
    assert out["stats"]["filled"] >= 55


def test_refresh_style_mdcr_limited_payload_no_crash() -> None:
    """Technický přehled se nesestřelí při minimálním slovníku MDČR."""
    vin = "WVGZZZ1TZ9W053855"
    vehicle = SimpleNamespace(
        vin=vin,
        brand="X",
        model="Y",
        year=2009,
        engine="e",
        plate="p",
        fuel="f",
        body_type="b",
        tyres_info="t",
    )
    out = build_vehicle_technical_overview(vehicle, mdcr_raw={"StatusNazev": "OK"}, local_decoded=None)
    assert out["stats"]["total"] >= 90

