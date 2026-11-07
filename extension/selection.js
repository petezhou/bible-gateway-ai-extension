(() => {
  const BOOKS = {
    Gen: 'Genesis', Exod: 'Exodus', Lev: 'Leviticus', Num: 'Numbers', Deut: 'Deuteronomy',
    Josh: 'Joshua', Judg: 'Judges', Ruth: 'Ruth', '1Sam': '1 Samuel', '2Sam': '2 Samuel',
    '1Kgs': '1 Kings', '2Kgs': '2 Kings', '1Chr': '1 Chronicles', '2Chr': '2 Chronicles',
    Ezra: 'Ezra', Neh: 'Nehemiah', Esth: 'Esther', Job: 'Job', Ps: 'Psalms', Prov: 'Proverbs',
    Eccl: 'Ecclesiastes', Song: 'Song of Solomon', Isa: 'Isaiah', Jer: 'Jeremiah', Lam: 'Lamentations',
    Ezek: 'Ezekiel', Dan: 'Daniel', Hos: 'Hosea', Joel: 'Joel', Amos: 'Amos', Obad: 'Obadiah',
    Jonah: 'Jonah', Mic: 'Micah', Nah: 'Nahum', Hab: 'Habakkuk', Zeph: 'Zephaniah', Hag: 'Haggai',
    Zech: 'Zechariah', Mal: 'Malachi', Matt: 'Matthew', Mark: 'Mark', Luke: 'Luke', John: 'John',
    Acts: 'Acts', Rom: 'Romans', '1Cor': '1 Corinthians', '2Cor': '2 Corinthians', Gal: 'Galatians',
    Eph: 'Ephesians', Phil: 'Philippians', Col: 'Colossians', '1Thess': '1 Thessalonians',
    '2Thess': '2 Thessalonians', '1Tim': '1 Timothy', '2Tim': '2 Timothy', Titus: 'Titus',
    Phlm: 'Philemon', Heb: 'Hebrews', Jas: 'James', '1Pet': '1 Peter', '2Pet': '2 Peter',
    '1John': '1 John', '2John': '2 John', '3John': '3 John', Jude: 'Jude', Rev: 'Revelation',
  };

  function verseKey(element) {
    for (const name of element.classList) {
      const match = name.match(/^((?:[1-3]-?)?[A-Za-z]+)-(\d+)-(\d+)$/);
      if (!match) continue;
      const book = match[1].replace('-', '');
      if (BOOKS[book] && Number(match[2]) > 0 && Number(match[3]) > 0) {
        return { book, chapter: Number(match[2]), verse: Number(match[3]) };
      }
    }
    return null;
  }

  function read(selection = window.getSelection()) {
    if (!selection || selection.isCollapsed || selection.rangeCount !== 1 || !selection.toString().trim()) return null;
    const range = selection.getRangeAt(0);
    const ancestor = range.commonAncestorContainer;
    const scope = ancestor.nodeType === Node.ELEMENT_NODE ? ancestor : ancestor.parentElement;
    if (!scope) return null;
    const candidates = [...scope.querySelectorAll('.passage-text .text, .text')];
    const containingVerse = scope.closest('.passage-text .text');
    if (containingVerse) candidates.unshift(containingVerse);
    const selected = [];
    const passages = new Set();
    for (const element of new Set(candidates)) {
      const passage = element.closest('.passage-text');
      const key = verseKey(element);
      if (!passage || !key || !range.intersectsNode(element)) continue;
      // intersectsNode can include a verse whose boundary merely touches the
      // range. Require a nonempty selected text node, excluding footnotes.
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      let node;
      let hasText = false;
      while ((node = walker.nextNode())) {
        if (node.parentElement.closest('.footnote, .crossreference, .crossrefs, .footnotes')) continue;
        if (!range.intersectsNode(node)) continue;
        const overlap = document.createRange();
        overlap.selectNodeContents(node);
        if (range.compareBoundaryPoints(Range.START_TO_START, overlap) > 0) {
          overlap.setStart(range.startContainer, range.startOffset);
        }
        if (range.compareBoundaryPoints(Range.END_TO_END, overlap) < 0) {
          overlap.setEnd(range.endContainer, range.endOffset);
        }
        if (range.intersectsNode(node) && overlap.toString().trim()) {
          hasText = true;
          break;
        }
      }
      if (hasText) {
        selected.push(key);
        passages.add(passage);
      }
    }
    if (!selected.length) return null;
    let error = '';
    if (passages.size !== 1) error = 'Highlight verses in one translation at a time.';
    if (selected.some((key) => key.book !== selected[0].book || key.chapter !== selected[0].chapter)) {
      error = 'Highlight verses within one chapter.';
    }
    const first = selected[0];
    const verses = [...new Set(selected.map((key) => key.verse))].sort((a, b) => a - b);
    if (!error && verses.some((verse, index) => index > 0 && verse !== verses[index - 1] + 1)) {
      error = 'Highlight a continuous range of verses.';
    }
    const start = `${first.book}.${first.chapter}.${verses[0]}`;
    const end = verses.at(-1);
    const rects = [...range.getClientRects()].filter((rect) => rect.width > 0 && rect.height > 0);
    return {
      reference: end === verses[0] ? start : `${start}-${first.book}.${first.chapter}.${end}`,
      label: `${BOOKS[first.book]} ${first.chapter}:${verses[0]}${end === verses[0] ? '' : `-${end}`}`,
      excerpt: selection.toString().trim().slice(0, 1200),
      rect: rects[0] || range.getBoundingClientRect(),
      error,
    };
  }

  function passage(table, column = table.closest('.passage-col')) {
    const match = (table.dataset.osis || '').match(/^([1-3]?[A-Za-z]+)\.(\d+)(?:\.(\d+))?(?:-([1-3]?[A-Za-z]+)\.(\d+)\.(\d+))?$/);
    if (!match || !BOOKS[match[1]]) return null;
    const [, book, chapter, start, endBook, endChapter, end] = match;
    if (endBook && (book !== endBook || chapter !== endChapter || Number(end) < Number(start))) return null;
    const heading = column?.querySelector('.passage-display .bcv')?.textContent.trim();
    const wholeChapter = !start || (heading && !heading.includes(':'));
    const reference = wholeChapter ? `${book}.${chapter}` : table.dataset.osis;
    const label = `${BOOKS[book]} ${chapter}${wholeChapter ? '' : `:${start}${end && end !== start ? `-${end}` : ''}`}`;
    return { reference, label, heading: column?.querySelector('.passage-display') };
  }

  window.BibleGatewayAISelection = { read, passage };
})();
