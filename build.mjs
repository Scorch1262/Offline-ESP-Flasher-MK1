// Baut das Frontend (esptool-js + xterm + eigene Oberfläche) zu einer
// einzigen, komplett offline lauffähigen JS- und CSS-Datei in web/dist/.
import * as esbuild from "esbuild";
import { readFileSync, mkdirSync, copyFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const esptoolPkg = JSON.parse(readFileSync("node_modules/esptool-js/package.json", "utf8"));

mkdirSync("web/dist", { recursive: true });

await esbuild.build({
  entryPoints: ["src/main.js"],
  bundle: true,
  format: "esm",
  target: ["chrome110", "edge110"],
  minify: true,
  sourcemap: false,
  outfile: "web/dist/app.js",
  legalComments: "linked",
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __ESPTOOL_VERSION__: JSON.stringify(esptoolPkg.version),
  },
  logLevel: "info",
});

copyFileSync("node_modules/@xterm/xterm/css/xterm.css", "web/dist/xterm.css");
console.log(`Frontend gebaut: v${pkg.version} (esptool-js ${esptoolPkg.version})`);
