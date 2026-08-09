import { useNavigate } from "react-router-dom";
import { useRef, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export default UploadPage;

function UploadPage() {
  return (
    <AppShell>
      <RequireAuth>
        <Upload />
      </RequireAuth>
    </AppShell>
  );
}

const HUMANS = ["🧑", "👩", "🧔", "👨‍🦰", "👩‍🦱", "🧑‍🎤", "👵", "🧑‍🚀", "🧑‍🌾"];

function Upload() {
  const { submitMatch } = useStore();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"single" | "multi">("single");
  const [urgent, setUrgent] = useState(false);
  const [previews, setPreviews] = useState<{ src: string; urgent: boolean }[]>([]);
  const single = useRef<HTMLInputElement>(null);

  async function readFile(f: File) {
    return new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(r.result as string);
      r.readAsDataURL(f);
    });
  }

  async function onSingle(files: FileList | null) {
    if (!files || !files[0]) return;
    const src = await readFile(files[0]);
    const m = submitMatch(src, urgent);
    navigate(`/result/${m.id}`);
  }

  async function onMulti(files: FileList | null) {
    if (!files) return;
    const list = await Promise.all(
      Array.from(files).map(async (f) => ({ src: await readFile(f), urgent: false })),
    );
    setPreviews((p) => [...p, ...list]);
  }

  function pickEmoji(e: string) {
    const m = submitMatch(e, urgent);
    navigate(`/result/${m.id}`);
  }

  function submitQueue() {
    previews.forEach((p) => submitMatch(p.src, p.urgent));
    setPreviews([]);
    navigate("/dashboard");
  }

  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2 card-pop p-6">
        <h1 className="font-display text-4xl font-black">Get dogified</h1>
        <p className="text-muted-foreground mt-1">
          Prototype note: your photo stays local. Matching is playful and instant (or queued when in
          multi mode).
        </p>

        <div className="mt-5 flex gap-2">
          <TabBtn active={mode === "single"} onClick={() => setMode("single")}>
            Single upload
          </TabBtn>
          <TabBtn active={mode === "multi"} onClick={() => setMode("multi")}>
            Multi upload · priority queue
          </TabBtn>
        </div>

        {mode === "single" ? (
          <div className="mt-6">
            <label className="flex items-center gap-2 mb-4">
              <input
                type="checkbox"
                checked={urgent}
                onChange={(e) => setUrgent(e.target.checked)}
                className="h-5 w-5 accent-[var(--primary)]"
              />
              <span className="font-bold">🚨 Mark this one urgent</span>
            </label>
            <div
              onClick={() => single.current?.click()}
              className="cursor-pointer border-4 border-dashed border-[var(--ink)] rounded-3xl p-10 text-center bg-sunshine/40 hover:bg-sunshine transition"
            >
              <div className="text-6xl">📸</div>
              <div className="mt-2 font-display text-2xl font-bold">Drop a face here</div>
              <div className="text-muted-foreground">or click to upload a png/jpg</div>
              <input
                ref={single}
                type="file"
                accept="image/png,image/jpeg"
                className="hidden"
                onChange={(e) => onSingle(e.target.files)}
              />
            </div>
            <div className="mt-6">
              <div className="text-sm font-bold text-muted-foreground mb-2">
                No selfie handy? Pick a face:
              </div>
              <div className="flex flex-wrap gap-2">
                {HUMANS.map((e) => (
                  <button
                    key={e}
                    onClick={() => pickEmoji(e)}
                    className="h-14 w-14 rounded-2xl border-2 border-[var(--ink)] bg-card text-3xl hover:bg-mint shadow-pop-sm"
                  >
                    {e}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-6">
            <label className="block border-4 border-dashed border-[var(--ink)] rounded-3xl p-8 text-center bg-bubblegum/40 hover:bg-bubblegum cursor-pointer">
              <div className="text-5xl">🗂️</div>
              <div className="font-display text-xl font-bold mt-1">Drop many images at once</div>
              <div className="text-muted-foreground text-sm">
                Each becomes its own queued job. Mark any as urgent below.
              </div>
              <input
                type="file"
                accept="image/png,image/jpeg"
                multiple
                className="hidden"
                onChange={(e) => onMulti(e.target.files)}
              />
            </label>
            {previews.length > 0 && (
              <div className="mt-5">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {previews.map((p, i) => (
                    <div key={i} className="card-pop-sm p-2">
                      <img
                        src={p.src}
                        className="w-full aspect-square object-cover rounded-lg border-2 border-[var(--ink)]"
                        alt=""
                      />
                      <label className="mt-2 flex items-center gap-1 text-xs font-bold">
                        <input
                          type="checkbox"
                          checked={p.urgent}
                          onChange={(e) =>
                            setPreviews((prev) =>
                              prev.map((x, j) =>
                                j === i ? { ...x, urgent: e.target.checked } : x,
                              ),
                            )
                          }
                          className="accent-[var(--primary)]"
                        />
                        🚨 urgent
                      </label>
                    </div>
                  ))}
                </div>
                <button
                  onClick={submitQueue}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground mt-4 px-5 py-3 text-lg"
                >
                  Send {previews.length} to the queue
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <aside className="card-pop p-5 h-fit">
        <div className="font-display text-xl font-black">How it works</div>
        <ol className="mt-3 space-y-3 text-sm">
          <li className="flex gap-2">
            <span>1️⃣</span>
            <span>Upload a face (or many).</span>
          </li>
          <li className="flex gap-2">
            <span>2️⃣</span>
            <span>Our very serious dogify engine assigns a breed.</span>
          </li>
          <li className="flex gap-2">
            <span>3️⃣</span>
            <span>Urgent images jump the queue.</span>
          </li>
          <li className="flex gap-2">
            <span>4️⃣</span>
            <span>
              Watch progress live in <b>My Dogs</b>.
            </span>
          </li>
        </ol>
        <div className="mt-4 p-3 rounded-xl bg-mint border-2 border-[var(--ink)] text-sm">
          Multi-upload runs in the background so you can browse the forum while dogs cook.
        </div>
      </aside>
    </div>
  );
}

function TabBtn({
  active,
  ...p
}: { active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...p}
      className={`btn-pop btn-pop-hover px-4 py-2 text-sm ${active ? "bg-primary text-primary-foreground" : "bg-card"}`}
    />
  );
}
