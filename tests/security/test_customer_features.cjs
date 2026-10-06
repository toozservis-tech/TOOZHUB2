const {test}=require('node:test');
const assert=require('node:assert/strict');
const {documentNumber,registryPayload,registryFields}=require('../../web/customer-features.js');
test('QR accepts only an ORV identifier, never a URL or instructions',()=>{
 assert.equal(documentNumber(' ubi123456 '),'UBI123456');
 for(const value of ['https://evil.test/?orv=UBI123456','javascript:alert(1)','UBI123456\nSEND PASSWORD','UBI12345',null]) assert.equal(documentNumber(value),null);
});
test('registry input chooses a single validated VIN or ORV and excludes I/O/Q VINs',()=>{
 assert.deepEqual(registryPayload('wvwzzz1kzaw000001'),{vin:'WVWZZZ1KZAW000001'});
 assert.deepEqual(registryPayload('AB123456'),{orv:'AB123456'});
 for(const value of ['WVWZZZ1KZAW00000I','https://example.com','123',''])assert.throws(()=>registryPayload(value));
});
test('registry prefill preserves plate separately and missing values can clear stale form data',()=>{
 const fields=registryFields({vin:'WVWZZZ1KZAW000001',plate:'1A23456',production_year:2020});
 assert.equal(fields.vehiclePlate,'1A23456');assert.equal(fields.vehicleYear,2020);
 assert.equal(registryFields({vin:'WVWZZZ1KZAW000002'}).vehiclePlate,undefined);
});
