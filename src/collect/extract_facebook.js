// extract_facebook.js — pull a post and its comment threads out of the page.
//
// Runs inside the Orca built-in browser via `orca eval`. Returns a JSON string.
//
// The shape of a Facebook comment node in the DOM:
//   div[role="article"][aria-label^="Comment by <Author> <time>"]
//     a[href~="profile"]        the author
//     a[href*="comment_id"]     the timestamp, href is the comment permalink
//     div[dir="auto"]           the author, the time, then the body (twice:
//                                the outer div and the inner span)
//     img[alt]                  a sticker or photo, when there is no text
//
// A comment with no text at all is a sticker reaction. It is kept, with an
// empty body, so the cleaning stage can drop it as X_EMPTY.

(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();

  const all = Array.from(document.querySelectorAll('div[role="article"]'));
  // A comment is not only the article whose label starts with "Comment by".
  // A comment also contains nested articles - the author's own article, for
  // one - and those have no label at all, so a label test alone classifies
  // them as posts. The caption then comes from a comment, which is how the
  // post text ended up being somebody else's remark.
  const COMMENT_SEL = 'div[role="article"][aria-label^="Comment by"]';
  const isComment = a => /^Comment by/.test(a.getAttribute('aria-label') || '')
                          || !!a.closest(COMMENT_SEL);

  const commentNodes = all.filter(isComment);
  const postNodes = all.filter(a => !isComment(a));

  // ---- the post itself ----------------------------------------------------
  let post = { post_text: '', post_url: location.href, post_date: '' };

  // The caption lives in the message container, which Facebook marks with
  // data-ad-comet-preview. That is the reliable place to read it from.
  for (const p of postNodes) {
    const msg = p.querySelector('[data-ad-comet-preview]');
    if (!msg) continue;
    const txt = clean(msg.innerText);
    if (txt) { post.post_text = txt.slice(0, 4000); break; }
  }

  if (!post.post_text) {
    // The label of the post's own article, when the layout provides one.
    for (const p of postNodes) {
      const label = p.getAttribute('aria-label') || '';
      if (!/^Post by|Shared with Public/i.test(label)) continue;
      const parts = Array.from(p.querySelectorAll('div[dir="auto"]'))
        .map(x => clean(x.innerText)).filter(Boolean);
      if (parts.length) { post.post_text = parts[0].slice(0, 4000); break; }
    }
  }

  if (!post.post_text) {
    // The last resort: the first piece of text in an article that is not
    // a comment and does not contain one. The comment test has to be
    // applied again here, because a comment's own nested article has no
    // label and would otherwise look like the post.
    for (const p of postNodes) {
      if (p.querySelector(COMMENT_SEL)) continue;
      const parts = Array.from(p.querySelectorAll('div[dir="auto"]'))
        .map(x => clean(x.innerText)).filter(Boolean);
      if (parts.length) { post.post_text = parts[0].slice(0, 4000); break; }
    }
  }
  const stamp = document.querySelector('abbr, span[data-utime]');
  if (stamp) post.post_date = clean(stamp.innerText);

  // ---- the comments -------------------------------------------------------
  const comments = [];
  for (const node of commentNodes) {
    const label = node.getAttribute('aria-label') || '';

    // The aria-label is "Comment by <author> <time>". The time can be
    // "51m", "about an hour ago", "2 hours ago", "yesterday" or a date, so
    // it is peeled off the end rather than matched with a fixed list.
    // Facebook writes the time in many shapes: "51m", "7 hours", "7 hours ago",
    // "about an hour ago", "yesterday", "Tuesday, 6 October 2026 at 4:00 PM".
    const TIME_TAIL = new RegExp(
      '\\s*((?:' +
      '\\d+\\s*(?:s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks|mo|mon|mons|y|yr|yrs)\\b' +
      '|\\d+\\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)(?:\\s+ago)?' +
      '|about an? \\w+ ago|an? \\w+ ago|just now|yesterday|today|last \\w+' +
      '|\\w+, \\w+ \\d+, \\d{4}(?: at \\d{1,2}:?\\d{2} ?[AP]M)?' +
      '|\\d{1,2}:?\\d{2}\\s*[AP]M' +
      '))\\s*$', 'i');
    let rest = label.replace(/^Comment by\s*/, '');
    let timestamp = '';
    const tm = rest.match(TIME_TAIL);
    if (tm) {
      timestamp = tm[1].trim();
      rest = rest.slice(0, tm.index);
    }
    let author = rest.trim();

    const dirAuto = Array.from(node.querySelectorAll('div[dir="auto"], span[dir="auto"]'))
      .map(x => clean(x.innerText)).filter(Boolean);

    // the author link is the first link whose text is not the timestamp
    let permalink = '';
    let profileLinkText = '';

    for (const a of node.querySelectorAll('a[href]')) {
      const href = a.getAttribute('href') || '';
      const txt = clean(a.innerText);
      if (href.includes('comment_id')) {
        permalink = href.split('?comment_id')[0] + '?comment_id=' +
          (href.split('comment_id=')[1] || '').split('&')[0];
        if (!timestamp) timestamp = txt;
      } else if (!profileLinkText && txt &&
                 !/^\d+\s*[smhdwmy]$/i.test(txt) &&
                 !/^\d{1,2}:?\d{2}\s*[AP]M$/i.test(txt)) {
        profileLinkText = txt;
      }
    }
    // the aria-label is the better source; the profile link is the fallback
    if (!author) author = profileLinkText;
    if (!timestamp && profileLinkText && profileLinkText !== author) {
      // nothing better available
    }

    // the body is the longest dir=auto node after the author and the time
    const BARE_TIME = /^(?:\d+\s*[smhdwmy]|just now|yesterday|today)$/i;
    const bodyParts = dirAuto.filter(t =>
      t !== author && t !== timestamp && !BARE_TIME.test(t));
    let body = '';
    for (const t of bodyParts) if (t.length > body.length) body = t;

    // a sticker or photo comment has no text; keep the alt so it is not blank
    let alt = '';
    if (!body) {
      const img = node.querySelector('img[alt]');
      if (img) alt = clean(img.getAttribute('alt')).slice(0, 300);
    }

    const text = body || alt;

    // a reply is a comment article nested inside another comment article
    const isReply = !!node.parentElement &&
      !!node.parentElement.closest('div[role="article"]');

    const full = clean(node.innerText);
    const edited = /(^|\s)Edited(\s|$)/.test(full);
    const hasTranslation = !!node.querySelector('a[href*="#"], [aria-label*="translation" i]') ||
      /See translation/i.test(full);

    comments.push({
      comment_text: text.slice(0, 4000),
      author_name: author.slice(0, 120),
      timestamp_raw: timestamp.slice(0, 60),
      permalink: permalink,
      is_reply: isReply,
      edited: edited,
      has_translation: hasTranslation,
    });
  }

  // Facebook renders a post permalink in a modal AND leaves the previous page
  // behind it, so the same comment can be in the DOM twice. Two comments by
  // the same person with the same text at the same time are the same comment.
  const seen = new Set();
  const unique = [];
  for (const c of comments) {
    // The time is deliberately not part of the key: the same comment is
    // rendered twice (in the overlay and in the page behind it) and the two
    // renders can show different relative times.
    const key = (c.author_name || '') + '\u0000' + (c.comment_text || '');
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(c);
  }
  comments.length = 0;
  comments.push(...unique);

  return JSON.stringify({
    url: location.href,
    title: document.title,
    post: post,
    n_comments: comments.length,
    n_raw_articles: commentNodes.length,
    comments: comments,
  });
})()
