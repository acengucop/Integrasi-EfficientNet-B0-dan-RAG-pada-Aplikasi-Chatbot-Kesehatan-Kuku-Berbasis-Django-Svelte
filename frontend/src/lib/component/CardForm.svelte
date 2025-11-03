<script lang="ts">
  import { onMount } from "svelte";

  // === ambil global dari CDN saat komponen ter-mount ===
  let Cropper: any = null;
  onMount(() => {
    Cropper = (window as any)?.Cropper ?? null;
  });

  // ==== Props dari parent ====
  export let imageURL: string;
  export let prompt: string;
  export let loading: boolean;
  export let errorMsg: string;
  export let onFileChange: (event: Event) => void;
  export let submit: () => Promise<void>;
  export let onReset: () => void;
  export let onCropped: (file: File, objectUrl: string) => void;

  // ==== Local state ====
  let showCrop = false;
  let imgEl: HTMLImageElement | null = null;
  let cropper: any = null;
  let aspect: "free" | "1:1" | "4:3" | "3:4" | "16:9" = "free";

  // Re-init cropper saat editor terbuka + ada imageURL
  $: if (showCrop && imageURL) {
    queueMicrotask(() => {
      destroyCropper();
      if (imgEl && Cropper) {
        cropper = new Cropper(imgEl, {
          viewMode: 1,
          dragMode: "move",
          autoCropArea: 0.9,
          background: false,
          responsive: true,
          zoomOnWheel: true,
          movable: true,
          cropBoxResizable: true,
          checkCrossOrigin: false,
        });
        applyAspect();
      }
    });
  }

  function destroyCropper() {
    try { cropper?.destroy?.(); } catch {}
    cropper = null;
  }

  function applyAspect() {
    if (!cropper) return;
    switch (aspect) {
      case "1:1": cropper.setAspectRatio?.(1); break;
      case "4:3": cropper.setAspectRatio?.(4/3); break;
      case "3:4": cropper.setAspectRatio?.(3/4); break;
      case "16:9": cropper.setAspectRatio?.(16/9); break;
      default:    cropper.setAspectRatio?.(NaN);
    }
  }

  async function applyCrop() {
    if (!cropper) return;
    const canvas = cropper.getCroppedCanvas?.({
      maxWidth: 1536,
      maxHeight: 1536,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high",
    });
    if (!canvas) return;

    const mime = "image/jpeg";
    const quality = 0.95;
    canvas.toBlob((blob: Blob | null) => {
      if (!blob) return;
      const file = new File([blob], "cropped.jpg", { type: mime });
      const url = URL.createObjectURL(file);
      onCropped?.(file, url);
      showCrop = false;
    }, mime, quality);
  }

  function resetCrop() { cropper?.reset?.(); }
  function zoomIn() { cropper?.zoom?.(0.1); }
  function zoomOut() { cropper?.zoom?.(-0.1); }
</script>

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
          on:change={(e: Event) => {
            onFileChange(e);
            showCrop = true;   // buka editor setelah pilih gambar
          }}
          class="block w-full text-sm file:mr-4 file:py-2 file:px-4
                 file:rounded-xl file:border-0 file:text-sm file:font-medium
                 file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100
                 cursor-pointer"
        />

        {#if imageURL}
          <!-- Toolbar crop -->
          <div class="mt-3 flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
              on:click={() => showCrop = !showCrop}
            >
              {showCrop ? "Tutup Editor" : "Edit & Crop"}
            </button>

            {#if showCrop}
              <div class="flex items-center gap-2">
                <label for="ratio" class="text-xs text-slate-600">Rasio:</label>
                <select
                  id="ratio"
                  bind:value={aspect}
                  on:change={applyAspect}
                  class="rounded-md border border-slate-300 text-xs px-2 py-1"
                >
                  <option value="free">Bebas</option>
                  <option value="1:1">1 : 1</option>
                  <option value="4:3">4 : 3</option>
                  <option value="3:4">3 : 4</option>
                  <option value="16:9">16 : 9</option>
                </select>

                <button type="button" class="rounded-md border px-2 py-1 text-xs hover:bg-slate-50" on:click={zoomOut}>- Zoom</button>
                <button type="button" class="rounded-md border px-2 py-1 text-xs hover:bg-slate-50" on:click={zoomIn}>+ Zoom</button>
                <button type="button" class="rounded-md border px-2 py-1 text-xs hover:bg-slate-50" on:click={resetCrop}>Reset</button>
                <button
                  type="button"
                  class="rounded-md bg-indigo-600 text-white px-3 py-1.5 text-xs hover:bg-indigo-700"
                  on:click={applyCrop}
                >
                  Terapkan Crop
                </button>
              </div>
            {/if}
          </div>

          <!-- Area editor crop / preview -->
          {#if showCrop}
            <div class="mt-3 rounded-xl border border-slate-200 overflow-hidden bg-slate-50">
              <div class="h-[320px] relative">
                <img bind:this={imgEl} src={imageURL} alt="crop source" class="block max-w-full" />
              </div>
            </div>
          {:else}
            <div class="mt-4">
              <img src={imageURL} alt="preview" class="max-h-64 rounded-xl border border-slate-200" />
            </div>
          {/if}
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
          const el = document.getElementById("hasil");
          if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
        disabled={loading}
        aria-busy={loading}
      >
        {#if loading}
          <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
            <path class="opacity-75" d="M4 12a 8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" fill="currentColor"></path>
          </svg>
          Memproses...
        {:else}
          Kirim
        {/if}
      </button>

      <button
        class="rounded-xl px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm"
        on:click={() => {
          destroyCropper();
          onReset();
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

<style>
  @media (min-width: 640px) { /* sm */
    .h-\[320px\] { height: 360px; }
  }
</style>
