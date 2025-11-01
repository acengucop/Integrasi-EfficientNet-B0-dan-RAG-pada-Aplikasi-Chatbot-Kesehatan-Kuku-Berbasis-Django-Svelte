<script lang="ts">
  import { onDestroy } from "svelte";
  import { marked } from "marked";
  import DOMPurify from "dompurify";

  // ==== Types ====
  interface AnalyzeResult {
    prediction: string;
    confidence: number;
    probs: Record<string, number>;
    explanation_md: string;
  }

  // ==== State ====
  let imageFile: File | null = null;
  let imageURL = "";
  let prompt = "";
  let loading = false;
  let errorMsg = "";
  let result: AnalyzeResult | null = null;

  const API_BASE: string =
    import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

  // ==== Utils ====

  // 1) Autolink citation [S1]/[L2] -> DOI/PubMed + autolink DOI polos
  function autolinkReferences(md: string): string {
    if (!md) return md;

    const tagToUrl = new Map<string, string>();
    // Tangkap baris referensi berisi DOI atau PMID
    const refLineRegex =
      /^\[([A-Z]\d+)\][^\n]*?((?:doi:\s*)?(10\.\d{4,9}\/[^\s\]\)]+)|PMID:\s*(\d+))/gim;

    let m: RegExpExecArray | null;
    while ((m = refLineRegex.exec(md)) !== null) {
      const tag = m[1];          // S1 / L2 / dst
      const doiRaw = m[3];       // 10.xxxx/...
      const pmid = m[4];         // angka PMID
      if (doiRaw) {
        const doi = doiRaw.replace(/\.$/, "");
        tagToUrl.set(tag, `https://doi.org/${doi}`);
      } else if (pmid) {
        tagToUrl.set(tag, `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`);
      }
    }

    let out = md;

    // Ganti citation in-text: [S1] -> [S1](URL) (hindari yang sudah bertaut)
    if (tagToUrl.size) {
      out = out.replace(/\[([A-Z]\d+)\](?!\()/g, (_full, tag: string) => {
        const url = tagToUrl.get(tag);
        return url ? `[${tag}](${url} "Buka tautan referensi")` : `[${tag}]`;
      });
    }

    // Autolink DOI polos atau "doi: ..."
    out = out.replace(
      /\b(?:doi:\s*)?(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)\b/gi,
      (_full, doi: string) => {
        const clean = doi.replace(/\.$/, "");
        return `[doi:${clean}](https://doi.org/${clean} "Buka DOI")`;
      }
    );

    return out;
  }

  // 2) Tambahkan target/rel ke semua <a> setelah sanitize (tanpa sentuh renderer API)
  function addExternalAttrs(html: string): string {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    wrapper.querySelectorAll<HTMLAnchorElement>("a").forEach((a) => {
      a.target = "_blank";
      // gabungkan kalau sudah punya rel lain
      const rel = new Set((a.getAttribute("rel") || "").split(/\s+/).filter(Boolean));
      rel.add("noopener"); rel.add("noreferrer");
      a.setAttribute("rel", Array.from(rel).join(" "));
    });
    return wrapper.innerHTML;
  }

  // 3) Render markdown + sanitize (cast hasil marked.parse ke string agar tidak union Promise)
  function renderMarkdownWithRefs(md: string): string {
    const linked = autolinkReferences(md);
    const raw = marked.parse(linked ?? "") as string; // <-- penting untuk hilangkan union Promise
    const safe = DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
    return addExternalAttrs(safe);
  }

  // 4) Sort probabilitas desc
  function sortedProbs(probs: Record<string, number>) {
    return Object.entries(probs).sort((a, b) => b[1] - a[1]);
  }

  // ==== Handlers ====
  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement | null;
    const f = input?.files?.[0] ?? null;
    imageFile = f;
    result = null;
    errorMsg = "";

    if (imageURL) URL.revokeObjectURL(imageURL);
    imageURL = imageFile ? URL.createObjectURL(imageFile) : "";
  }

  async function submit() {
    errorMsg = "";
    result = null;

    if (!imageFile) {
      errorMsg = "Pilih gambar kuku terlebih dahulu.";
      return;
    }

    loading = true;
    const form = new FormData();
    form.append("image", imageFile);
    form.append("prompt", prompt || "");

    try {
      const res = await fetch(`${API_BASE}/analyze`, { method: "POST", body: form });
      if (!res.ok) {
        const errJson: { detail?: string } = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }
      const data: AnalyzeResult = await res.json();
      result = data;
    } catch (e: unknown) {
      errorMsg = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  onDestroy(() => {
    if (imageURL) URL.revokeObjectURL(imageURL);
  });
</script>


<!-- Page wrapper -->
<div class="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 text-slate-800">
  <!-- Header -->
  <header class="border-b border-slate-200 bg-white/70 backdrop-blur sticky top-0 z-10">
    <div class="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
      <h1 class="text-xl sm:text-2xl font-bold tracking-tight">
        <span class="bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-purple-600">
          NailBot
        </span>
        <span class="text-slate-500 font-medium"> · Analisis Penyakit Kuku</span>
      </h1>
      <a
        href="http://localhost:8000/api/labels"
        target="_blank"
        rel="noopener noreferrer"
        class="text-sm text-indigo-600 hover:text-indigo-700"
      >
        Cek /api/labels
      </a>
    </div>
  </header>

  <!-- Main -->
  <main class="max-w-5xl mx-auto px-4 py-8 space-y-6">
    <!-- Card: Form -->
    <section>
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 sm:p-6">
        <h2 class="text-lg font-semibold mb-4">Unggah Gambar & Prompt</h2>

        <div class="grid sm:grid-cols-2 gap-5">
          <!-- File input -->
          <div>
            <label for="file" class="block text-sm font-medium mb-2">Gambar kuku (JPG/PNG)</label>
            <input
              id="file"
              type="file"
              accept="image/*"
              on:change={onFileChange}
              class="block w-full text-sm file:mr-4 file:py-2 file:px-4
                     file:rounded-xl file:border-0 file:text-sm file:font-medium
                     file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100
                     cursor-pointer"
            />
            {#if imageURL}
              <div class="mt-4">
                <img src={imageURL} alt="preview" class="max-h-64 rounded-xl border border-slate-200" />
              </div>
            {/if}
          </div>

          <!-- Prompt -->
          <div>
            <label for="prompt" class="block text-sm font-medium mb-2">Prompt tambahan (opsional)</label>
            <textarea
              id="prompt"
              rows="8"
              bind:value={prompt}
              placeholder="Contoh: Jelaskan gejala umum & kapan perlu ke tenaga kesehatan. Gunakan bahasa sederhana."
              class="w-full rounded-xl border border-slate-300 focus:border-indigo-500 focus:ring-indigo-500 text-sm p-3"
            ></textarea>
            <p class="text-xs text-slate-500 mt-2">
              Penjelasan akan tetap non-diagnostik dan menyertakan disclaimer.
            </p>
          </div>
        </div>

        <!-- Actions -->
        <div class="mt-6 flex items-center gap-3">
          <button
            class="inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5
                   bg-indigo-600 text-white font-medium hover:bg-indigo-700
                   focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
            on:click={async () => {
              await submit();
              const el = document.getElementById('hasil');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
            disabled={loading}
            aria-busy={loading}
          >
            {#if loading}
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
                <path class="opacity-75" d="M4 12a 8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" fill="currentColor"/>
              </svg>
              Memproses...
            {:else}
              Kirim
            {/if}
          </button>

          <button
            class="rounded-xl px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm"
            on:click={() => {
              imageFile = null;
              result = null;
              errorMsg = "";
              prompt = "";
              if (imageURL) { URL.revokeObjectURL(imageURL); imageURL = ""; }
            }}
            disabled={loading}
          >
            Reset
          </button>
        </div>

        <!-- Error -->
        {#if errorMsg}
          <div class="mt-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 p-3 text-sm">
            {errorMsg}
          </div>
        {/if}
      </div>
    </section>

    <!-- Card: Hasil (di bawah form) -->
    <section id="hasil">
      <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 sm:p-6">
        <h2 class="text-lg font-semibold mb-1">Hasil</h2>
        <p class="text-xs text-slate-500 mb-4">Non-diagnostik · Untuk edukasi umum saja</p>

        {#if !result}
          <p class="text-sm text-slate-500">
            Belum ada hasil. Unggah gambar dan tulis prompt, lalu klik <b>Kirim</b>.
          </p>
        {:else}
          <!-- Ringkas di atas -->
          <dl class="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden">
            <div class="grid grid-cols-3 sm:grid-cols-6 gap-4 p-4">
              <dt class="col-span-1 text-xs uppercase tracking-wide text-slate-500">Kategori</dt>
              <dd class="col-span-2 sm:col-span-5 text-base font-semibold">
                {result.prediction}
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
                  {#each sortedProbs(result.probs) as [k, v]}
                    <li>
                      <div class="flex items-center justify-between text-sm">
                        <span class="text-slate-700">{k}</span>
                        <span class="font-mono tabular-nums">{(v * 100).toFixed(1)}%</span>
                      </div>
                      <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div class="h-full bg-indigo-500" style={`width:${(v*100).toFixed(1)}%`} />
                      </div>
                    </li>
                  {/each}
                </ul>
              </dd>
            </div>

            <div class="p-4">
              <dt class="text-xs uppercase tracking-wide text-slate-500 mb-2">Penjelasan</dt>
              <dd
                class="prose prose-sm max-w-none prose-headings:mt-3 prose-headings:mb-2
                       prose-p:my-2 prose-li:my-0 text-slate-800"
              >
                {@html renderMarkdownWithRefs(result.explanation_md || "")}
              </dd>
            </div>
          </dl>

          <!-- Sumber/Disclaimer kecil di bawah -->
          <div class="mt-4 text-[13px] text-slate-500">
            <p>
              Informasi ini bersifat edukasi umum dan <span class="font-medium">bukan</span> pengganti konsultasi medis.
            </p>
          </div>
        {/if}
      </div>
    </section>
  </main>

  <footer class="py-8 text-center text-xs text-slate-500">
    © {new Date().getFullYear()} NailBot · Non-diagnostic assistant
  </footer>
</div>
