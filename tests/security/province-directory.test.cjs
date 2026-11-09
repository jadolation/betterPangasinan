const test=require('node:test');const assert=require('node:assert/strict');
const {allowed}=require('../../scripts/province-directory.cjs');
test('directory browser excludes unrelated origins and credentials',()=>{
 assert.equal(allowed('https://www.pangasinan.gov.ph/directory/'),true);
 for(const u of ['http://www.pangasinan.gov.ph/','https://evil.test/','https://user@www.pangasinan.gov.ph/','file:///tmp/a'])assert.equal(allowed(u),false);
});
test('plain rendered emails and two-column hospital contacts are retained',()=>{
 const {contacts}=require('../../scripts/province-directory.cjs');
 const result=contacts([{cells:['Name','Contact Number']},{cells:['Test office','123','office@example.invalid']},{cells:['Test hospital','456']}]);
 assert.equal(result.length,2);assert.deepEqual(result[0].emails,['office@example.invalid']);assert.deepEqual(result[1].emails,[]);
});
