import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // AVIF primero (más ligero que WebP para la foto del hero); WebP para los navegadores sin AVIF.
    formats: ["image/avif", "image/webp"],
  },
};

export default nextConfig;
