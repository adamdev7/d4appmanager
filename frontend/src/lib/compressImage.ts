const MAX_SIDE = 1400;
const JPEG_QUALITY = 0.88;

async function bitmapFromFile(file: File): Promise<{ width: number; height: number; draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void; close: () => void } | null> {
  try {
    const bitmap = await createImageBitmap(file);
    return {
      width: bitmap.width,
      height: bitmap.height,
      draw: (ctx, w, h) => ctx.drawImage(bitmap, 0, 0, w, h),
      close: () => bitmap.close(),
    };
  } catch {
    try {
      const url = URL.createObjectURL(file);
      const image = await new Promise<HTMLImageElement>((resolve, reject) => {
        const node = new Image();
        node.onload = () => resolve(node);
        node.onerror = () => reject(new Error("decode"));
        node.src = url;
      });
      URL.revokeObjectURL(url);
      return {
        width: image.naturalWidth || image.width,
        height: image.naturalHeight || image.height,
        draw: (ctx, w, h) => ctx.drawImage(image, 0, 0, w, h),
        close: () => undefined,
      };
    } catch {
      return null;
    }
  }
}

export async function compressProductPhoto(file: File): Promise<File> {
  if (file.size < 32) return file;
  const source = await bitmapFromFile(file);
  if (!source || source.width < 1 || source.height < 1) return file;
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(source.width, source.height));
    const width = Math.max(1, Math.round(source.width * scale));
    const height = Math.max(1, Math.round(source.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    source.draw(ctx, width, height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY)
    );
    if (!blob || blob.size < 32) return file;
    if (blob.size >= file.size && (file.type === "image/jpeg" || file.type === "image/jpg")) {
      return file;
    }
    const base = file.name.replace(/\.[^.]+$/, "") || "product";
    return new File([blob], `${base}.jpg`, { type: "image/jpeg" });
  } finally {
    source.close();
  }
}
