import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dossier de compilation séparable (instance de test isolée sans gêner l'application principale)
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
