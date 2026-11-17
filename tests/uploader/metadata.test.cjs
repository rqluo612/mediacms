const assert = require('node:assert/strict');
const {tags, validate} = require('../../static/js/upload-metadata.js').UploadMetadata;
assert.deepEqual(tags(' Science ,science， 自然   科学 '), ['science', '自然 科学']);
assert.equal(validate({title:'视频', tags:['a','b'], description:''}), '');
for (const value of [
    {title:' ', tags:['a','b'], description:''},
    {title:'字'.repeat(101), tags:['a','b'], description:''},
    {title:'视频', tags:[], description:''},
    {title:'视频', tags:['a','b','c','d','e','f'], description:''},
    {title:'视频', tags:['a'.repeat(21),'b'], description:''},
    {title:'视频', tags:['a','b'], description:'字'.repeat(301)}
]) assert.notEqual(validate(value), '');
assert.equal(validate({title:'字'.repeat(100), tags:['字'.repeat(20),'b'], description:'字'.repeat(300)}), '');
console.log('Upload metadata normalization and validation checks passed.');

assert.equal(validate({title:'视频', tags:tags('A, a'), description:''}), '');
for (const name of ['a.jpg','a.mp3','a.pdf']) assert.equal(require('../../static/js/upload-metadata.js').UploadMetadata.isVideo(name), false);
