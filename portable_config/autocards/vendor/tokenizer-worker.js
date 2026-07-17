/* Off-main-thread kuromoji tokenizer.
 *
 * The IPADIC dictionary is ~13 MB gzipped and kuromoji inflates it + builds a
 * DoubleArray trie in pure JS. Doing that on the UI thread freezes subtitle
 * playback for a second or two. Running it here keeps the main thread smooth:
 * the page renders subtitles immediately and highlighting applies once the
 * worker signals ready. Only the five fields the analyzer needs are returned,
 * to keep the postMessage payload small. */
importScripts('/vendor/kuromoji.js');

var tokenizer = null;

function trim(t) {
  return {
    surface_form: t.surface_form,
    pos: t.pos,
    pos_detail_1: t.pos_detail_1,
    basic_form: t.basic_form,
    reading: t.reading
  };
}

kuromoji.builder({ dicPath: '/vendor/dict' }).build(function (err, built) {
  if (err) {
    self.postMessage({ type: 'error', message: String((err && err.message) || err) });
    return;
  }
  tokenizer = built;
  self.postMessage({ type: 'ready' });
});

self.onmessage = function (e) {
  var msg = e.data;
  if (!msg || msg.type !== 'tokenize' || !tokenizer) return;
  // msg.lines: array of lines; each line is an array of sublines (strings).
  var result = msg.lines.map(function (sublines) {
    return sublines.map(function (s) {
      return tokenizer.tokenize(s).map(trim);
    });
  });
  self.postMessage({ type: 'tokens', id: msg.id, result: result });
};
