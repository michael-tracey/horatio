import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Button, Card, ErrorText, Field, Input, Loaded, Textarea } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useAction } from "../../hooks";

type DesignOut = components["schemas"]["EmailDesignOut"];
type Defaults = components["schemas"]["EmailDesignDefaults"];

const DESIGN = ["site", "email-design"];
const MAIL = ["site", "mail"];
const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

export type DesignForm = {
  site_name: string;
  header_colour: string;
  header_text_colour: string;
  accent: string;
  footer: string;
};

/** What to save: a part left as Horatio's own is sent blank, so it follows the default. */
export function designBody(form: DesignForm, defaults: Defaults): DesignForm {
  const own = (value: string, fallback: string) => (value.trim().toLowerCase() === fallback.toLowerCase() ? "" : value.trim());
  return {
    site_name: own(form.site_name, defaults.site_name),
    header_colour: own(form.header_colour, defaults.header_colour),
    header_text_colour: own(form.header_text_colour, defaults.header_text_colour),
    accent: own(form.accent, defaults.accent),
    footer: form.footer.trim(),
  };
}

/**
 * How every email Horatio sends looks (#830): a header with the site's name or a
 * picture, its colours and an accent, and a short footer, around what each email
 * says. Shown as a mail client would show it, light or dark, phone or desktop, and
 * sent to the custodian to see for real.
 */
export function EmailDesignCard() {
  const design = useQuery({
    queryKey: DESIGN,
    queryFn: () => unwrap(api.GET("/api/site/email-design")),
  });
  return <Loaded query={design}>{(found) => <DesignShown design={found} />}</Loaded>;
}

function DesignShown({ design }: { design: DesignOut }) {
  return (
    <Card title="Email design">
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-mist">
          Every email Horatio sends, from password resets to downtime results, comes in this design: as a formatted email, and as plain text for mail apps that
          want it. Under your footer, each email still says why it came and how to stop it, and that Horatio sent it.
        </p>
        <DesignFields design={design} />
        <HeaderPicture design={design} />
        <Preview />
        <TestDesign />
      </div>
    </Card>
  );
}

function DesignFields({ design }: { design: DesignOut }) {
  const toast = useToast();
  const from = (d: DesignOut): DesignForm => ({
    site_name: d.site_name,
    header_colour: d.header_colour,
    header_text_colour: d.header_text_colour,
    accent: d.accent,
    footer: d.footer,
  });
  const [form, setForm] = useState<DesignForm>(from(design));
  useEffect(() => setForm(from(design)), [design]);
  const set = (part: keyof DesignForm) => (value: string) => setForm((f) => ({ ...f, [part]: value }));
  const save = useAction((body: DesignForm) => unwrap(api.PUT("/api/site/email-design", { body })), [DESIGN]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(designBody(form, design.defaults), {
      onSuccess: () => toast({ message: "Saved. Every email from now on looks like this." }),
    });
  };
  const putBack = () =>
    save.mutate(
      {
        site_name: "",
        header_colour: "",
        header_text_colour: "",
        accent: "",
        footer: form.footer.trim(),
      },
      {
        onSuccess: () => toast({ message: "Horatio's own name and colours are back." }),
      },
    );
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t border-ash pt-4">
      <h3 className="text-parchment">Header, colours and footer</h3>
      <Field label="Site's name" hint={`In the header, unless a picture is there. Blank: ${design.defaults.site_name}.`}>
        <Input value={form.site_name} maxLength={design.site_name_max} onChange={(e) => set("site_name")(e.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Colour label="Header colour" value={form.header_colour} onChange={set("header_colour")} />
        <Colour label="Header's text colour" value={form.header_text_colour} onChange={set("header_text_colour")} />
        <Colour
          label="Accent"
          hint="Buttons and the line under the header. Links use it, darkened if they must be to read."
          value={form.accent}
          onChange={set("accent")}
        />
      </div>
      {design.warnings.map((warning) => (
        <p key={warning} className="text-xs text-blood-bright">
          {warning}
        </p>
      ))}
      <Field
        label="Footer"
        hint={`Up to ${design.footer_max} characters: who runs this Horatio, how to reach them. **Bold**, *italic*, [words](https://…) and links work. ${form.footer.length}/${design.footer_max}`}
      >
        <Textarea rows={3} maxLength={design.footer_max} value={form.footer} onChange={(e) => set("footer")(e.target.value)} />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending}>
          Save the design
        </Button>
        {design.chosen.some((part) => part !== "footer") && (
          <Button type="button" variant="ghost" disabled={save.isPending} onClick={putBack}>
            Put back Horatio's name and colours
          </Button>
        )}
      </div>
      <ErrorText error={save.error} />
    </form>
  );
}

function Colour({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (value: string) => void }) {
  return (
    <Field label={label} hint={hint}>
      <Input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-10 w-full cursor-pointer p-1" />
    </Field>
  );
}

function HeaderPicture({ design }: { design: DesignOut }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState(false);
  const upload = useAction(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return unwrap(
        api.POST("/api/site/email-design/header", {
          body: form as never,
          bodySerializer: (body: unknown) => body as FormData,
        }),
      );
    },
    [DESIGN],
  );
  const remove = useAction(() => unwrap(api.DELETE("/api/site/email-design/header")), [DESIGN]);
  const image = design.header_image;
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <h3 className="text-parchment">Header picture</h3>
      {image && (
        <div className="flex flex-col gap-1">
          <img
            src={image.url}
            alt="The emails' header picture"
            className="w-full max-w-md rounded-md border border-ash"
            style={{ background: design.header_colour }}
          />
          <p className="text-xs text-mist">
            {image.width} × {image.height} px, {Math.round(image.size / 1024)} KB in every email.
          </p>
        </div>
      )}
      {design.uploads ? (
        <>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            aria-label="Choose a header picture"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              setTooBig(file.size > MAX_BYTES);
              if (file.size <= MAX_BYTES) upload.mutate(file);
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
              {upload.isPending ? "Uploading…" : image ? "Upload a new header picture" : "Add a header picture"}
            </Button>
            {image && (
              <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
                Remove the header picture
              </Button>
            )}
          </div>
          <p className="text-xs text-mist">
            Optional: a logo or banner in place of the site's name, on the header colour. It's made at most 1200 × 400 px and kept small, as a PNG or JPEG, and
            goes inside every email rather than being fetched from Horatio. Where a mail app blocks pictures, the site's name shows instead.
          </p>
        </>
      ) : (
        <p className="text-xs text-mist">Pictures aren't set up on this server, so emails show the site's name in the header.</p>
      )}
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      <ErrorText error={upload.error ?? remove.error} />
    </div>
  );
}

/** A sample email in the design, in a sealed frame: light or dark, phone or desktop. */
function Preview() {
  const [scheme, setScheme] = useState<"light" | "dark">("light");
  const [width, setWidth] = useState<"phone" | "desktop">("desktop");
  const [plain, setPlain] = useState(false);
  const shown = useQuery({
    queryKey: [...DESIGN, "preview", scheme],
    queryFn: () =>
      unwrap(
        api.GET("/api/site/email-design/preview", {
          params: { query: { scheme } },
        }),
      ),
  });
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <h3 className="text-parchment">Preview</h3>
      <div className="flex flex-wrap gap-4 text-xs">
        <Choice
          label="Colours"
          value={scheme}
          options={[
            ["light", "Light"],
            ["dark", "Dark"],
          ]}
          onChange={setScheme}
        />
        <Choice
          label="Width"
          value={width}
          options={[
            ["phone", "Phone"],
            ["desktop", "Desktop"],
          ]}
          onChange={setWidth}
        />
        <Choice
          label="Part"
          value={plain ? "plain" : "html"}
          options={[
            ["html", "Formatted"],
            ["plain", "Plain text"],
          ]}
          onChange={(v) => setPlain(v === "plain")}
        />
      </div>
      <Loaded query={shown}>
        {(found) =>
          plain ? (
            <pre
              aria-label="The email as plain text"
              className="max-h-96 overflow-auto rounded-md border border-ash bg-night p-3 text-xs whitespace-pre-wrap text-parchment"
            >
              {found.text}
            </pre>
          ) : (
            <iframe
              title="Preview of an email in the design"
              sandbox=""
              srcDoc={found.html}
              className="h-[32rem] max-w-full rounded-md border border-ash bg-white"
              style={{ width: width === "phone" ? 375 : 680 }}
            />
          )
        }
      </Loaded>
    </div>
  );
}

function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (value: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex items-center gap-1">
      <span className="mr-1 text-mist">{label}</span>
      {options.map(([key, words]) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          onClick={() => onChange(key)}
          className={`rounded-md border px-2 py-1 ${value === key ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment"}`}
        >
          {words}
        </button>
      ))}
    </div>
  );
}

function TestDesign() {
  const mail = useQuery({
    queryKey: MAIL,
    queryFn: () => unwrap(api.GET("/api/site/mail")),
  });
  const test = useAction(() => unwrap(api.POST("/api/site/email-design/test")), [MAIL]);
  if (!mail.data?.on) return null;
  const result = test.data;
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" disabled={test.isPending} onClick={() => test.mutate(undefined)}>
          Send me this email
        </Button>
        <span className="text-xs text-mist">The sample above, to your own address, to see it in your mail app.</span>
      </div>
      <div role="status" className="flex flex-col gap-1">
        {result?.ok && <p className="text-parchment">Sent to {result.to}. If it doesn't arrive, look in its spam folder.</p>}
        {result && !result.ok && (
          <>
            <p className="text-blood-bright">{result.reason}</p>
            {result.detail && <p className="font-mono text-xs break-words text-mist">The server said: {result.detail}</p>}
          </>
        )}
      </div>
      <ErrorText error={test.error} />
    </div>
  );
}
