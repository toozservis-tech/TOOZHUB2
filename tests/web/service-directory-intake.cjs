const assert=require('node:assert/strict');
const {matchesRegisteredService,safePlaceUrl,usablePlaceId,intakeVehiclePayload,consentTitle,publicServiceError}=require('../../web/service-features.js');
let checks=0;
function check(actual,expected){assert.deepEqual(actual,expected);checks++;}
const registered={id:7,name:'Servis Šťastný',city:'Litomyšl',street:'Tichá',zip:'57001',ico:'12345678'};
check(matchesRegisteredService(registered,'STASTNY'),true);
check(matchesRegisteredService(registered,'litomysl'),true);
check(matchesRegisteredService(registered,'12345678'),true);
check(matchesRegisteredService(registered,''),true);
check(matchesRegisteredService(registered,'Cizí servis'),false);
check(safePlaceUrl('https://maps.apple.com/?daddr=49.2%2C16.2'),'https://maps.apple.com/?daddr=49.2%2C16.2');
for(const url of ['javascript:alert(1)','https://evil.example/maps.apple.com','https://maps.apple.com.evil.example/','https://user:password@maps.apple.com/','http://maps.apple.com/','not a url'])check(safePlaceUrl(url),null);
check(usablePlaceId('ABC_123.place:7'),true);
for(const id of ['',null,'bad id','x'.repeat(129),'<script>'])check(usablePlaceId(id),false);
const vehicle={nickname:'  První auto  ',vin:' tmb12345678901234 ',plate:' 1A23456 ',year:'2020',current_mileage_km:'125000',last_stk_mileage_km:'120000',stk_valid_until:'2028-04-22'};
const payload=intakeVehiclePayload(vehicle,{invite:true});
check(payload.nickname,'První auto');check(payload.vin,'TMB12345678901234');check(payload.current_mileage_km,125000);check(payload.year,2020);
check(intakeVehiclePayload({nickname:'Druhé auto',vin:'HISTORIC1'}).vin,'HISTORIC1');
check(intakeVehiclePayload({nickname:'Druhé auto'}).vin,null);
for(const values of [{nickname:'A'},{nickname:'Auto',year:'1899'},{nickname:'Auto',year:'2101'},{nickname:'Auto',current_mileage_km:'-1'},{nickname:'Auto',current_mileage_km:'3.5'},{nickname:'Auto',current_mileage_km:'5',last_stk_mileage_km:'6'}]){assert.throws(()=>intakeVehiclePayload(values));checks++;}
for(const vin of ['','SHORT','TMB1234567890123I']){assert.throws(()=>intakeVehiclePayload({nickname:'Auto',vin},{invite:true}));checks++;}
assert.equal('invite_email' in payload,false);assert.equal('customer_id' in payload,false);assert.equal('service_access' in payload,false);checks+=3;
check(consentTitle('awaiting_registration'),'Čeká na registraci majitele · pouze u servisu');
check(consentTitle('future_unknown_state'),'Stav souhlasu není dostupný');
check(consentTitle('approved'),'Sdíleno s majitelem');
for(const subject of ['home','map']){const message=publicServiceError({status:503,message:'Missing table customer_home_garages; run migration'},subject);check(/customer_home_garages|migration/.test(message),false);}
console.log(`Service directory/intake boundaries: ${checks} checks passed`);
