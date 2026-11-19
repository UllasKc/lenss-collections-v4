// ---------------------------------------------------------------- "i" info tips (v4)
// A small "i" next to each Gen-AI metric in Observability: hover, keyboard focus or a tap shows
// what the metric means and how it is computed. One dictionary, one helper (window.infoTip),
// one floating tip shared by every page. Texts must match the code that computes each metric
// (server/lib/judge.ts, server/lib/evals.ts, the answer cache): change both together.

(function setupInfoTips() {
  const TIPS = {
    groundedness: ['Groundedness score',
      'Average faithfulness of the answers judged in this period. Green at 90% or more; an answer under the warning threshold (70%) gets a warning and is listed under Low-confidence answers.',
      "Each answer's faithfulness is the mean of the numbers check and the judge's faithfulness, or whichever of the two exists."],
    reconciliation: ['Numeric reconciliation',
      "Share of the figures in answers that were found in the answers' own query results. No AI model is involved.",
      'Figures found ÷ figures checked. Each number is looked up in the results, allowing for rounding, K/M/B, crore/lakh and % formats, column totals and group subtotals. Small counts, years, business-rule thresholds and numbers typed in the question are skipped.'],
    faithfulness: ['Faithfulness (judge)',
      'Share of the factual claims in an answer that its query results support.',
      'Scored by the answer-quality judge model on every live answer; it also lists up to 5 claims it could not find in the results.'],
    relevance: ['Relevance',
      'Does the answer address the question that was asked?',
      'Scored 0 to 1 by the answer-quality judge on every live answer.'],
    completeness: ['Completeness',
      'Does the answer cover every part of the question?',
      'Scored 0 to 1 by the judge. Below 70% the Assistant offers "Go deeper".'],
    safety: ['Safety',
      "Is the answer free of personal data, abuse, and claims the data can't back, such as forecasts, causal uplift or probabilities?",
      'Scored 0 to 1 by the answer-quality judge.'],
    unsupported: ['Unsupported claims',
      'Claims in an answer that the judge could not find in its query results.',
      'Listed by the judge, up to 5 per answer.'],
    lowConfidence: ['Low-confidence answers',
      'Answers whose faithfulness scored below the warning threshold (70%). Open one to see its trace.',
      'Faithfulness = mean of the numbers check and the judge, or whichever exists.'],
    latency: ['Latency',
      'How long live answers take, from question to answer. Answers served from the cache are not counted.',
      'Typical (p50): half finish within this time. Most (p90): 9 in 10. Almost all (p95): 19 in 20.'],
    cache: ['Cache hits / served instantly',
      'Questions answered from the semantic answer cache, with no call to the query engine.',
      'A new question is matched to a cached one by GTE Large embeddings at 98% similarity or more, for the same data and semantic-model versions.'],
    tokens: ['Tokens',
      'The units AI models read and write: about 4 characters each, counted in and out, per feature.',
      'Totalled from each model call the app makes. The query engine is billed with the SQL warehouse and is not counted here.'],
    accuracy: ['Accuracy (evals)',
      "Share of ground-truth questions the Assistant answered correctly.",
      "Each case's answer is compared with the results of its ground-truth SQL; a case passes when correctness is 80% or more."],
    correctness: ['Correctness',
      'Share of the ground-truth figures the answer matched.',
      'The figures returned by the ground-truth SQL are matched against the answer; 80% or more passes the case.'],
    guardrails: ['Guardrails (evals)',
      'Red-team questions blocked, and normal questions not blocked.',
      'Each case is run through the input guardrails and compared with its expected outcome (block, redact or allow). Uses only the classifier model.'],
    policy: ['Policy checks',
      'Answer-wording rules, such as no forecasts, probabilities or cure rates.',
      'Sample answers are checked by the policy rules and compared with the expected flag. No AI model is involved.'],
    routing: ['Routing',
      'Conversations sent to the expected place: platform help, a quick answer or a deep analysis.',
      "Each case's conversation goes through the question router and is compared with its expected route. Uses only the router model."],
  };
  window.INFO_TIPS = TIPS;

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  /** The "i" button for a metric, as HTML: put it right after the metric's label. */
  window.infoTip = (key) => (TIPS[key]
    ? `<button type="button" class="itip" data-tip="${key}" aria-label="About ${esc(TIPS[key][0])}" aria-describedby="infoTipBox">i</button>`
    : '');

  const box = document.createElement('div');
  box.id = 'infoTipBox';
  box.className = 'info-tip';
  box.setAttribute('role', 'tooltip');
  box.hidden = true;
  document.body.appendChild(box);
  let pinned = null;

  function show(btn) {
    const t = TIPS[btn.dataset.tip];
    if (!t) return;
    box.innerHTML = `<span class="info-tip-k">${esc(t[0])}</span><span class="info-tip-d">${esc(t[1])}</span><span class="info-tip-h"><b>How it's computed:</b> ${esc(t[2])}</span>`;
    box.hidden = false;
    const r = btn.getBoundingClientRect();
    const w = Math.min(340, window.innerWidth - 24);
    box.style.maxWidth = w + 'px';
    const left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12));
    box.style.left = left + 'px';
    const below = r.bottom + 8;
    box.style.top = (below + box.offsetHeight > window.innerHeight - 8 ? Math.max(8, r.top - box.offsetHeight - 8) : below) + 'px';
  }
  const hide = () => { box.hidden = true; pinned = null; };

  document.addEventListener('mouseover', (e) => { const b = e.target.closest('.itip'); if (b && !pinned) show(b); });
  document.addEventListener('mouseout', (e) => { const b = e.target.closest('.itip'); if (b && !pinned && !b.contains(e.relatedTarget)) box.hidden = true; });
  document.addEventListener('focusin', (e) => { const b = e.target.closest('.itip'); if (b) show(b); });
  document.addEventListener('focusout', (e) => { if (e.target.closest('.itip') && !pinned) box.hidden = true; });
  // A tap (touch) or click pins the tip until the next tap elsewhere or Escape.
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.itip');
    if (b) { e.preventDefault(); e.stopPropagation(); if (pinned === b) hide(); else { pinned = b; show(b); } return; }
    if (pinned) hide();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !box.hidden) hide(); });
  window.addEventListener('scroll', () => { if (!box.hidden) hide(); }, { passive: true, capture: true });
})();
