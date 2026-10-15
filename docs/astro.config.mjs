import { defineConfig } from "astro/config";
import mermaid from "astro-mermaid";
import starlight from "@astrojs/starlight";
import starlightVersions from "starlight-versions";
import { unified } from "@astrojs/markdown-remark";

export default defineConfig({
  site: "https://natlabrockies.github.io",
  base: "/R2X/",
  markdown: { processor: unified() },
  redirects: {
    "/how-to/troubleshooting/": "/R2X/troubleshooting/",
    "/reference/changelog/": "/R2X/changelog/",
  },
  integrations: [
    mermaid({
      enableLog: false,
      mermaidConfig: {
        theme: "base",
        fontFamily: "system-ui, sans-serif",
        flowchart: { curve: "basis", nodeSpacing: 35, rankSpacing: 45, padding: 16 },
      },
    }),
    starlight({
      title: "R2X",
      description: "Translation plugins for ReEDS, PLEXOS, and Sienna model interoperability.",
      logo: {
        light: "./src/assets/r2x-logo-full-color.svg",
        dark: "./src/assets/r2x-logo-white.svg",
        alt: "R2X",
        replacesTitle: true,
      },
      social: [{ icon: "github", label: "GitHub", href: "https://github.com/NatLabRockies/R2X" }],
      editLink: {
        baseUrl: "https://github.com/NatLabRockies/R2X/edit/main/",
      },
      customCss: ["./src/styles/brand.css"],
      plugins: [
        starlightVersions({
          current: { label: "Latest (main)" },
          versions: [
            { slug: "2-2-0", label: "v2.2.0", redirect: "root" },
            { slug: "2-0-0", label: "v2.0.0", redirect: "root" },
          ],
        }),
      ],
      sidebar: [
        {
          label: "Getting started",
          items: [
            { label: "Introduction", link: "/" },
            { label: "Prerequisites", link: "/getting-started/prerequisites/" },
            { label: "Installation", link: "/getting-started/installation/" },
            { label: "First CLI pipeline", link: "/tutorials/getting-started/" },
          ],
        },
        {
          label: "Tutorials",
          items: [
            { label: "ReEDS with the CLI", link: "/tutorials/reeds-to-sienna-cli/" },
          ],
        },
        {
          label: "How-to guides",
          items: [
            { label: "Workflow overview", link: "/how-to/" },
            { label: "Inspect a system", link: "/how-to/inspect-transformed-system/" },
            { label: "ReEDS to PLEXOS", link: "/how-to/reeds-to-plexos/" },
            { label: "ReEDS to Sienna", link: "/how-to/reeds-to-sienna/" },
            { label: "PLEXOS to Sienna", link: "/how-to/plexos-to-sienna/" },
            { label: "Sienna to PLEXOS", link: "/how-to/sienna-to-plexos/" },
          ],
        },
        { label: "Troubleshooting", link: "/troubleshooting/" },
        {
          label: "Reference",
          items: [
            { label: "Python API", link: "/reference/python-api/" },
            { label: "ReEDS translation comparison", link: "/reference/reeds-translation-reference/" },
            { label: "ReEDS to PLEXOS properties", link: "/reference/reeds-to-plexos-properties/" },
            { label: "ReEDS to Sienna properties", link: "/reference/reeds-to-sienna-properties/" },
            { label: "PLEXOS to Sienna properties", link: "/reference/plexos-to-sienna-properties/" },
            { label: "Sienna to PLEXOS properties", link: "/reference/sienna-to-plexos-properties/" },
          ],
        },
        {
          label: "Explanation",
          items: [{ label: "Architecture", link: "/explanation/architecture/" }],
        },
        { label: "Changelog", link: "/changelog/" },
        { label: "Development", link: "/how-to/development/" },
      ],
    }),
  ],
});
