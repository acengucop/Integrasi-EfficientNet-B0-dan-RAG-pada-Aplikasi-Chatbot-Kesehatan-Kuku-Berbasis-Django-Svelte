<script lang="ts">
  import { onDestroy } from "svelte";
  import Penjelasan from "./lib/component/penjelasan.svelte";
  import CardForm from "./lib/component/CardForm.svelte";

  // ==== Types ====
  interface AnalyzeResult {
    prediction: string;
    confidence: number;
    probs: Record<string, number>;
    explanation_md: string;
    prompt_on_domain?: boolean; // optional dari backend
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

  // dipanggil CardForm saat user menekan "Terapkan Crop"
  function onCropped(file: File, url: string) {
    // ganti file & preview yang akan dikirim ke backend
    imageFile = file;
    // bersihkan preview lama
    if (imageURL && imageURL.startsWith("blob:")) URL.revokeObjectURL(imageURL);
    imageURL = url;
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

      // scroll ke hasil
      requestAnimationFrame(() => {
        const el = document.getElementById("hasil");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (e: unknown) {
      errorMsg = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function resetForm() {
    imageFile = null;
    result = null;
    errorMsg = "";
    prompt = "";
    if (imageURL) {
      URL.revokeObjectURL(imageURL);
      imageURL = "";
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
    <CardForm
      {imageURL}
      bind:prompt={prompt}
      {loading}
      {errorMsg}
      onFileChange={onFileChange}
      submit={submit}
      onReset={resetForm}
      onCropped={onCropped}  
    />

    <!-- Card: Hasil (komponen terpisah) -->
    <Penjelasan {result} {prompt} />
  </main>

  <footer class="py-8 text-center text-xs text-slate-500">
    © {new Date().getFullYear()} NailBot · Non-diagnostic assistant
  </footer>
</div>
