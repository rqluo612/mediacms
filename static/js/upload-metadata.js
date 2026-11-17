/* Shared normalization follows Tag.save: letters, numbers and collapsed spaces. */
(function(root) {
    function tags(value) {
        return [...new Set(value.split(/[,，]/).map(function(s) {
            return s.replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/gu, ' ').trim().toLowerCase();
        }).filter(Boolean))];
    }
    function isVideo(name) { return !/\.(jpe?g|png|gif|webp|bmp|svg|tiff?|mp3|wav|ogg|flac|aac|m4a|pdf)$/i.test(name); }
    function validate(data) {
        if (!data.title.trim() || Array.from(data.title.trim()).length > 100) return '标题必填，最多100字。';
        if (data.tags.length < 1 || data.tags.length > 5) return '至少1个、最多5个，建议填写2～3个';
        if (data.tags.some(function(t) { return Array.from(t).length > 20; })) return '每个标签最多20字。';
        if (Array.from(data.description).length > 300) return '简介最多300字。';
        return '';
    }
    root.UploadMetadata = {tags: tags, validate: validate, isVideo: isVideo};
})(typeof module !== 'undefined' ? module.exports : window);
