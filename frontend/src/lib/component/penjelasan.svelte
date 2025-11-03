<script lang="ts">
  import { marked } from "marked";
  import DOMPurify from "dompurify";

  interface AnalyzeResult {
    prediction: string;
    confidence: number;
    probs: Record<string, number>;
    explanation_md: string;
    prompt_on_domain?: boolean;
  }
  export let result: AnalyzeResult | null = null;
  export let prompt: string = "";

  let toc: { id: string; text: string }[] = [];
  marked.setOptions({ gfm: true, breaks: false });

  function autolinkReferences(md: string): string {
    if (!md) return md;
    const tagToUrl = new Map<string, string>();
    const refLineRegex =
      /^\[([A-Z]\d+)\][^\n]*?((?:doi:\s*)?(10\.\d{4,9}\/[^\s\]\)]+)|PMID:\s*(\d+))/gim;
    let m: RegExpExecArray | null;
    while ((m = refLineRegex.exec(md)) !== null) {
      const tag = m[1];
      const doiRaw = m[3];
      const pmid = m[4];
      if (doiRaw) tagToUrl.set(tag, `https://doi.org/${doiRaw.replace(/\.$/, "")}`);
      else if (pmid) tagToUrl.set(tag, `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`);
    }
    let out = md;
    if (tagToUrl.size) {
      out = out.replace(/\[([A-Z]\d+)\](?!\()/g, (_f, tag: string) => {
        const url = tagToUrl.get(tag);
        return url ? `[${tag}](${url} "Buka tautan referensi")` : `[${tag}]`;
      });
    }
    out = out.replace(/\b(?:doi:\s*)?(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)\b/gi,
      (_f, doi: string) => `[doi:${doi.replace(/\.$/, "")}](https://doi.org/${doi.replace(/\.$/, "")} "Buka DOI")`
    );
    return out;
  }

  const slug = (s: string) =>
    s.toLowerCase().trim()
      .replace(/[^\p{L}\p{N}\s-]/gu, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-");

  function enhanceHtml(html: string): string {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html;

    // ext links
    wrapper.querySelectorAll<HTMLAnchorElement>("a").forEach((a) => {
      a.target = "_blank";
      const rel = new Set((a.getAttribute("rel") || "").split(/\s+/).filter(Boolean));
      rel.add("noopener"); rel.add("noreferrer");
      a.setAttribute("rel", Array.from(rel).join(" "));
    });

    // TOC & anchor icon
    toc = [];
    wrapper.querySelectorAll<HTMLHeadingElement>("h2, h3").forEach((h) => {
      const text = h.textContent ?? "";
      const id = slug(text);
      if (!h.id) h.id = id;
      if (h.tagName.toLowerCase() === "h2") toc.push({ id, text });

      if (!h.querySelector("a.anchor")) {
        const a = document.createElement("a");
        a.className = "anchor";
        a.href = `#${id}`;
        a.setAttribute("aria-label", "Tautan ke bagian ini");
        a.innerHTML = `
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M3.9,12a5,5,0,0,1,5-5h3V4H8.9A8,8,0,0,0,8.9,20h3V17H8.9A5,5,0,0,1,3.9,12Zm6,1h4V11h-4Zm5.2-6H15v3h3a5,5,0,0,1,0,10H15v3h3a8,8,0,0,0,0-16Z"/>
          </svg>`;
        h.appendChild(a);
      }
    });

    return wrapper.innerHTML;
  }

  function renderMarkdownWithRefs(md: string): string {
    const linked = autolinkReferences(md);
    const raw = marked.parse(linked ?? "") as string;
    const safe = DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
    return enhanceHtml(safe);
  }

  function sortedProbs(probs: Record<string, number>) {
    return Object.entries(probs).sort((a, b) => b[1] - a[1]);
  }

  function lowConfidence(conf: number) { return conf < 0.70; }

  function promptMismatch(r: AnalyzeResult | null, userPrompt: string) {
    if (!r || !userPrompt.trim()) return false;
    if (typeof r.prompt_on_domain === "boolean") return !r.prompt_on_domain;
    return /tidak terkait dengan domain kuku|di luar konteks kuku/i.test(r.explanation_md || "");
  }
</script>

<section id="hasil">
  <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 sm:p-6">
    <h2 class="text-lg font-semibold mb-1">Hasil</h2>
    <p class="text-xs text-slate-500 mb-4">Non-diagnostik · Untuk edukasi umum saja</p>

    {#if !result}
      <p class="text-sm text-slate-500">
        Belum ada hasil. Unggah gambar dan tulis prompt, lalu klik <b>Kirim</b>.
      </p>
    {:else}
      <!-- Alerts -->
      {#if promptMismatch(result, prompt)}
        <div class="mb-4 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 p-3 text-sm">
          Prompt yang Anda masukkan tampaknya <b>di luar konteks kuku</b>. Penjelasan difokuskan pada hasil analisis kuku.
        </div>
      {/if}

      {#if lowConfidence(result.confidence)}
        <div class="mb-4 rounded-xl border border-yellow-300 bg-yellow-50 text-yellow-800 p-3 text-sm">
          Keyakinan model di bawah <b>0,70</b>. Mohon gunakan hasil dengan hati-hati dan pertimbangkan evaluasi lanjutan.
        </div>
      {/if}

      <div class="grid lg:grid-cols-12 gap-6">
        <!-- Left: Summary -->
        <div class="lg:col-span-8">
          <dl class="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden">
            <div class="grid grid-cols-3 sm:grid-cols-6 gap-4 p-4">
              <dt class="col-span-1 text-xs uppercase tracking-wide text-slate-500">Kategori</dt>
              <dd class="col-span-2 sm:col-span-5 text-base font-semibold">
                {result.prediction}
                <span class="ml-2 inline-flex items-center rounded-full bg-indigo-50 text-indigo-700 px-2 py-0.5 text-xs border border-indigo-200">
                  Top-1
                </span>
              </dd>
            </div>
            <div class="grid grid-cols-3 sm:grid-cols-6 gap-4 p-4">
              <dt class="col-span-1 text-xs uppercase tracking-wide text-slate-500">Confidence</dt>
              <dd class="col-span-2 sm:col-span-5 text-base font-semibold">
                {(result.confidence * 100).toLocaleString('id-ID', { maximumFractionDigits: 1 })}%
              </dd>
            </div>

            <div class="p-4">
              <dt class="text-xs uppercase tracking-wide text-slate-500 mb-2">Probabilitas per kelas</dt>
              <dd>
                <ul class="space-y-2">
                  {#each sortedProbs(result.probs) as [k, v], i}
                    <li>
                      <div class="flex items-center justify-between text-sm">
                        <span class="text-slate-700">{k}</span>
                        <span class="font-mono tabular-nums">{(v * 100).toFixed(1)}%</span>
                      </div>
                      <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          class={`h-full ${i === 0 ? 'bg-indigo-500' : 'bg-slate-300'}`}
                          style={`width:${(v * 100).toFixed(1)}%`}
                        ></div>
                      </div>
                    </li>
                  {/each}
                </ul>
              </dd>
            </div>

            <div class="p-4">
              <dt class="text-xs uppercase tracking-wide text-slate-500 mb-2">Penjelasan</dt>
              <dd
                class="prose prose-sm max-w-none leading-relaxed
                       prose-headings:mt-6 prose-headings:mb-3
                       prose-h2:text-slate-800 prose-h3:text-slate-800
                       prose-p:my-3 prose-li:my-1 prose-ul:my-3 prose-ol:my-3
                       prose-a:text-indigo-700 hover:prose-a:text-indigo-800
                       text-slate-800"
              >
                {@html renderMarkdownWithRefs(result.explanation_md || "")}
              </dd>
            </div>
          </dl>

          <div class="mt-4 text-[13px] text-slate-500">
            <p>
              Informasi ini bersifat edukasi umum dan <span class="font-medium">bukan</span> pengganti konsultasi medis.
            </p>
          </div>
        </div>

        <!-- Right: Mini TOC -->
        <aside class="lg:col-span-4 lg:sticky lg:top-20 h-fit">
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h3 class="text-sm font-semibold text-slate-700 mb-3">Daftar Isi</h3>
            {#if toc.length === 0}
              <p class="text-xs text-slate-500">Bagian akan muncul setelah penjelasan dirender.</p>
            {:else}
              <ol class="text-sm divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
                {#each toc as item, idx}
                  <li class="flex items-center gap-3 px-3 py-2 hover:bg-slate-50">
                    <span class="inline-flex h-6 w-6 items-center justify-center rounded-full bg-indigo-50 text-indigo-700 text-xs border border-indigo-200">
                      {idx + 1}
                    </span>
                    <a href={`#${item.id}`} class="flex-1 text-slate-700 hover:text-indigo-700">
                      {item.text}
                    </a>
                  </li>
                {/each}
              </ol>
            {/if}
          </div>
        </aside>
      </div>
    {/if}
  </div>
</section>


<style>
  /* Anchor icon: tampil saat hover di heading, posisinya rapi */
  :global(.prose h2, .prose h3) {
    position: relative;
    scroll-margin-top: 6rem; /* biar pas saat di-scroll dari TOC */
  }
  :global(.prose h2 .anchor), :global(.prose h3 .anchor) {
    position: absolute;
    left: -1.5rem;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0;
    transition: opacity .15s ease;
    color: #94a3b8; /* slate-400 */
    text-decoration: none;
  }
  :global(.prose h2:hover .anchor), :global(.prose h3:hover .anchor) {
    opacity: 1;
  }

  /* Spasi paragraf/list sedikit lebih longgar agar nyaman dibaca */
  :global(.prose p) { line-height: 1.7; }
  :global(.prose ul), :global(.prose ol) { padding-left: 1.25rem; }

  /* Blockquote (jika ada) */
  :global(.prose blockquote) {
    border-left: 3px solid #e5e7eb; /* slate-200 */
    padding-left: .875rem;
    color: #475569; /* slate-600 */
    font-style: normal;
  }
</style>
