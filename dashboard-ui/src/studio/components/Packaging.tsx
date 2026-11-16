import { Section, Segmented } from "./Forms";
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
 * How the code ships: a zip, or a container image in the cloud's registry (Amazon ECR, Azure Container Registry).
 * Shows the provider's size limits so a large bundle can switch to an image before a deploy fails.
 */
export function PackagingPanel({
  provider,
  draft,
  onChange,
}: {
  provider: ProviderMeta | undefined;
  draft: JsonObject;
  onChange: (next: JsonObject) => void;
}) {
  if (!provider || provider.name === "onprem") return null;
  const pkg = provider.package;
  const current = packageTypeOf(draft);
  const registry = pkg?.image_registry || "";
  const limits = pkg?.limits;
  const zipLimits = [
    limits?.zip_compressed ? `${formatLimit(limits.zip_compressed)} zipped` : "",
    limits?.zip_unpacked ? `${formatLimit(limits.zip_unpacked)} unzipped` : "",
  ].filter(Boolean);
  const soonTitle = `Container images on ${provider.display_name}: coming soon${pkg?.image_soon ? ` (${pkg.image_soon})` : ""}`;
  return (
    <Section title="Packaging" hint={`package.type: ${current}`} defaultOpen={current !== "zip"}>
      <div className="stack">
        <div className="row-gap wrap">
          <Segmented<PackageType>
            label="Package type"
            value={current}
            onChange={(v) => onChange(withPackageType(draft, v))}
            options={[
              { value: "zip", label: "Zip", title: "Upload the bundle as a zip (default)" },
              { value: "image", label: registry ? `Container image (${registry.replace(/ \(.*\)$/, "")})` : "Container image", disabled: !registry, title: registry ? `Build an image with Docker and push it to ${registry}` : soonTitle },
              { value: "auto", label: "Auto", disabled: !registry, title: registry ? "Zip, switching to an image when the bundle is over the zip limit" : soonTitle },
            ]}
          />
          {!registry && <span className="badge badge-off">images coming soon</span>}
        </div>
        <ul className="bullets small">
          <li>
            <b>Zip</b>
            {zipLimits.length ? (
              <>
                : up to {zipLimits.join(", ")} on {provider.display_name}
                {limits?.reference ? <span className="muted"> ({limits.reference})</span> : null}.
              </>
            ) : (
              <>: no size limit checked by pskit on {provider.display_name}.</>
            )}{" "}
            Package and Deploy print the bundle size against these limits; Deploy stops when a zip is over them.
          </li>
          {registry ? (
            <li>
              <b>Container image</b>: pskit builds the bundle into an image with your local Docker, pushes it to <b>{registry}</b>
              {limits?.image ? <> (images up to {formatLimit(limits.image)})</> : null} and points the functions at it. Needs Docker running where
              pskit runs. <b>Auto</b> stays a zip until the bundle is too big. One-off: <code className="mono">pskit deploy --package-type image</code>.
            </li>
          ) : (
            <li>{soonTitle}. Until then, keep the bundle small with <code className="mono">package.exclude</code> and fewer dependencies.</li>
          )}
          {provider.name === "azure" && current !== "zip" && (
            <li>
              Consumption plans cannot run containers: the app runs on Elastic Premium <b>EP1</b> unless <code className="mono">provider.options.plan_sku</code> is
              another non-Consumption plan (EP2/EP3, B1, S1, P1v3...).
            </li>
          )}
        </ul>
        {current !== "zip" && !registry && (
          <div className="hint-box warn">
            pskit.yml asks for <code className="mono">package.type: {current}</code>, which {provider.display_name} does not support yet.
            {current === "image" ? " Validate and Deploy fail until it is Zip." : " It stays a zip here."}
          </div>
        )}
      </div>
    </Section>
  );
}
