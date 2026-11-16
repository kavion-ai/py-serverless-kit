import { Segmented } from "./Forms";
import type { JsonObject, PackageType, ProviderMeta } from "../types";
import { asObject, str } from "../util";

/** Bytes as "250 MB" / "10 GB". */
export function formatLimit(bytes: number | null | undefined): string {
  if (!bytes) return "";
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${Number.isInteger(gb) ? gb : gb.toFixed(1)} GB`;
  const mb = bytes / 1024 ** 2;
  return `${Number.isInteger(mb) ? mb : mb.toFixed(1)} MB`;
}

/** `package.type` of pskit.yml (zip when unset). */
export function packageTypeOf(draft: JsonObject): PackageType {
  const kind = str(asObject(asObject(draft).package).type);
  return kind === "image" || kind === "auto" ? kind : "zip";
}

/** The draft with `package.type` set (zip removes the key: it is the default). */
export function withPackageType(draft: JsonObject, kind: PackageType): JsonObject {
  const pkg: JsonObject = { ...asObject(draft.package) };
  if (kind === "zip") delete pkg.type;
  else pkg.type = kind;
  const next: JsonObject = { ...draft };
  if (Object.keys(pkg).length) next.package = pkg;
  else delete next.package;
  return next;
}

/**
 * `shared_function_host` providers (Azure: one Function App) ship every function the same way: a package type chosen
 * in one function's editor becomes `package.type` and the per-function values are dropped.
 */
export function withSharedPackageType(draft: JsonObject, kind: PackageType): JsonObject {
  const next = withPackageType(draft, kind);
  const functions = asObject(next.functions);
  const cleaned: JsonObject = {};
  for (const [name, fn] of Object.entries(functions)) {
    const body: JsonObject = { ...asObject(fn) };
    delete body.package_type;
    cleaned[name] = body;
  }
  if (Object.keys(functions).length) next.functions = cleaned;
  return next;
}

/**
 * Function editor: `functions.<name>.package_type` (inherit = `package.type`), the only place the package type is
 * chosen. Image / auto need a provider with container images. On one-host providers (Azure) the choice applies to
 * every function (`package.type`, see {@link withSharedPackageType}).
 */
export function FunctionPackageField({
  value,
  draft,
  provider,
  onChange,
}: {
  value: string | undefined;
  draft: JsonObject;
  provider: ProviderMeta | undefined;
  onChange: (v: PackageType | undefined) => void;
}) {
  const pkg = provider?.package;
  const registry = pkg?.image_registry || "";
  const shared = !!provider?.shared_function_host;
  const inherited = packageTypeOf(draft);
  const current = value === "zip" || value === "image" || value === "auto" ? value : "inherit";
  const effective = current === "inherit" ? inherited : current;
  const name = provider?.display_name || "this provider";
  const soon = `Container images on ${name}: coming soon${pkg?.image_soon ? ` (${pkg.image_soon})` : ""}`;
  const limits = pkg?.limits;
  const zipLimits = [
    limits?.zip_compressed ? `${formatLimit(limits.zip_compressed)} zipped` : "",
    limits?.zip_unpacked ? `${formatLimit(limits.zip_unpacked)} unzipped` : "",
  ].filter(Boolean);
  return (
    <div className="stack">
      <Segmented<string>
        label="Package type"
        value={current}
        onChange={(v) => onChange(v === "inherit" ? undefined : (v as PackageType))}
        options={[
          { value: "inherit", label: `inherit (${inherited})` },
          { value: "zip", label: "Zip", title: "Ship the code as a zip" },
          { value: "image", label: registry ? `Image (${registry.replace(/ \(.*\)$/, "")})` : "Image", disabled: !registry, title: registry ? `Build an image with Docker and push it to ${registry}` : soon },
          { value: "auto", label: "Auto", disabled: !registry, title: registry ? "Zip, or an image when the bundle is over the zip limit" : soon },
        ]}
      />
      <span className="muted small">
        Zip: {zipLimits.length ? <>up to {zipLimits.join(", ")}</> : <>no size limit checked by pskit</>} on {name}.
        {registry ? (
          <> Image: built with your local Docker (needs Docker running) and pushed to {registry}{limits?.image ? <>, up to {formatLimit(limits.image)}</> : null}.</>
        ) : (
          <> {soon}.</>
        )}
      </span>
      {shared && (
        <span className="muted small">
          {name} runs every function in one app, so this choice applies to <b>every</b> function (<code className="mono">package.type</code>).
        </span>
      )}
      {provider?.name === "azure" && effective !== "zip" && (
        <span className="muted small">
          Consumption plans cannot run containers: the app runs on Elastic Premium <b>EP1</b> unless <code className="mono">provider.options.plan_sku</code> is another non-Consumption plan.
        </span>
      )}
    </div>
  );
}
