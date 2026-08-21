import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { DogOption, QuestionPrompt } from "@/components/game/DogOption";
import { HumanFace } from "@/components/game/HumanFace";
import { Leaderboard } from "@/components/game/Leaderboard";
import { MatchBoard } from "@/components/game/MatchBoard";
import { Podium, Scoreboard } from "@/components/game/Scoreboard";
import { TimerBar } from "@/components/game/TimerBar";
import type { GameType } from "@/lib/gameApi";
import { useGameRoom } from "@/lib/gameSocket";
import { useAuth } from "@/lib/auth";
import { useSecondsLeft } from "@/lib/useCountdown";

export default Room;

const OPTION_LABELS = ["1", "2", "3", "4"];
const ROUND_CHOICES = [5, 8, 10, 15, 20];
const SECOND_CHOICES = [10, 15, 20];
const MATCH_SECOND_CHOICES = [30, 45, 60];
const NOTICE_MS = 3500;

const GAME_LABEL: Record<GameType, string> = {
  double: "Spot the double",
  match: "Mix & match",
};

function Room() {
  return (
    <AppShell>
      <Inner />
    </AppShell>
  );
}

function Inner() {
  const { id } = useParams();
  const { user } = useAuth();
  const me = user!;
  const navigate = useNavigate();

  const { status, state, lastEvent, notice, clearNotice, serverNow, send } = useGameRoom({
    roomId: id,
  });

  // What *I* clicked. The server decides whether it counted; this only stops me
  // hammering the same question and shows my choice back to me.
  const [picked, setPicked] = useState<number | null>(null);
  // Claims I've sent that the server hasn't ruled on yet, drawn dashed. Cleared
  // by the ack or the rejection — never assumed to have worked.
  const [pending, setPending] = useState<Record<number, number>>({});

  // Only on a new round: `picked` has to survive into the reveal, or the ❌ and
  // the red ring on the answer you actually gave never get drawn.
  useEffect(() => {
    setPicked(null);
    setPending({});
  }, [state?.questionNumber]);

  // Anything still in flight is moot the moment the round closes.
  useEffect(() => {
    if (state?.phase !== "question") setPending({});
  }, [state?.phase]);

  useEffect(() => {
    if (lastEvent?.type !== "claim_ack" && lastEvent?.type !== "claim_rejected") return;
    const human = Number(lastEvent.payload.human);
    setPending((current) => {
      const next = { ...current };
      delete next[human];
      return next;
    });
  }, [lastEvent]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(clearNotice, NOTICE_MS);
    return () => window.clearTimeout(t);
  }, [notice, clearNotice]);

  const phase = state?.phase;
  const question = state?.question ?? null;
  const board = state?.board ?? null;
  const isMatch = state?.gameType === "match";

  const claim = useCallback(
    (human: number, dog: number) => {
      setPending((current) => ({ ...current, [human]: dog }));
      send("claim", { humanSlot: human, dogSlot: dog });
    },
    [send],
  );

  const release = useCallback(
    (human: number) => {
      setPending((current) => {
        const next = { ...current };
        delete next[human];
        return next;
      });
      send("release", { humanSlot: human });
    },
    [send],
  );

  const answer = useCallback(
    (choice: number) => {
      if (phase !== "question" || !question || picked !== null) return;
      setPicked(choice);
      send("answer", { questionIndex: question.index, choice });
    },
    [phase, question, picked, send],
  );

  // Mix & Match brings its own keys; this is the four-option question's.
  useEffect(() => {
    if (isMatch || phase !== "question" || !question || picked !== null) return;
    const onKey = (e: KeyboardEvent) => {
      const index = OPTION_LABELS.indexOf(e.key);
      if (index >= 0 && index < question.options.length) {
        e.preventDefault();
        answer(index);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isMatch, phase, question, picked, answer]);

  const leave = () => {
    send("leave");
    navigate("/lobbies");
  };

  const isHost = state?.hostId === String(me.id);
  const meRow = state?.players.find((p) => p.playerId === String(me.id));
  const submitted = state?.players.filter((p) => p.submitted).length ?? 0;
  const countdown = useSecondsLeft(
    phase === "countdown" ? (state?.endsAt ?? null) : null,
    serverNow,
  );

  if (!state) {
    return (
      <div className="card-pop max-w-md mx-auto p-8 text-center">
        <div className="text-5xl">{status === "open" ? "🐕" : "🔌"}</div>
        <h1 className="font-display text-2xl font-black mt-2">
          {status === "open" ? "Joining the room…" : "Connecting…"}
        </h1>
        {notice && <p className="text-sm font-bold mt-2">{notice}</p>}
        <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-4 py-2 mt-4 inline-block">
          Back to lobbies
        </Link>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start">
      <div className="space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
              Room
            </div>
            <h1 className="font-display text-3xl font-black truncate">{state.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            {phase !== "lobby" && phase !== "over" && (
              <div className="btn-pop bg-sunshine px-3 py-1 text-sm">
                Round {state.questionNumber} / {state.roundsTotal}
              </div>
            )}
            {/* The game-over card has its own "Back to lobbies", which does
                exactly this — no need to offer it twice on the same screen. */}
            {phase !== "over" && (
              <button onClick={leave} className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
                Leave
              </button>
            )}
          </div>
        </header>

        {status !== "open" && (
          <div className="card-pop-sm bg-sky p-3 text-sm font-bold">
            Reconnecting… your score is safe on the server.
          </div>
        )}
        {notice && (
          <div className="card-pop-sm bg-destructive text-destructive-foreground p-3 text-sm font-bold">
            {notice}
          </div>
        )}

        {phase === "lobby" && (
          <div className="card-pop p-8 text-center">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
              Room code
            </div>
            <div className="font-display text-6xl font-black tracking-[0.25em] mt-1">
              {state.code}
            </div>
            <p className="text-muted-foreground mt-2">
              Others join from <strong>Multiplayer</strong> with this code — phones included.
            </p>
            <p className="mt-3 text-sm font-bold">
              {isMatch
                ? "🔗 Mix & match — four people, four dogs. Pairing one claims it: nobody else can use that combination, but both tiles stay in play. You won't find out who was right until the round ends."
                : "🎯 Spot the double — one person, four dogs, everyone answers at once. Faster is worth more."}
            </p>

            {isHost ? (
              <div className="mt-6 space-y-4">
                <div className="flex flex-wrap gap-2 justify-center">
                  {(["double", "match"] as GameType[]).map((type) => (
                    <button
                      key={type}
                      onClick={() => send("set_options", { gameType: type })}
                      className={`btn-pop btn-pop-hover px-4 py-2 text-sm ${
                        state.gameType === type ? "bg-primary text-primary-foreground" : "bg-card"
                      }`}
                    >
                      {type === "match" ? "🔗 " : "🎯 "}
                      {GAME_LABEL[type]}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-4 justify-center">
                  <Chooser
                    label="Rounds"
                    values={ROUND_CHOICES}
                    current={state.roundsTotal}
                    onPick={(v) => send("set_options", { roundsTotal: v })}
                  />
                  <Chooser
                    label={isMatch ? "Seconds a board" : "Seconds each"}
                    values={isMatch ? MATCH_SECOND_CHOICES : SECOND_CHOICES}
                    current={state.secondsPerQuestion}
                    onPick={(v) => send("set_options", { secondsPerQuestion: v })}
                  />
                </div>
                <button
                  onClick={() => send("start")}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-8 py-3 text-lg"
                >
                  Start game →
                </button>
              </div>
            ) : (
              <p className="mt-6 font-bold">Waiting for the host to start…</p>
            )}
          </div>
        )}

        {phase === "countdown" && (
          <div className="card-pop p-16 text-center">
            <div className="font-display text-8xl font-black">{countdown || "Go!"}</div>
            <p className="text-muted-foreground mt-2">Get ready…</p>
          </div>
        )}

        {(phase === "question" || phase === "reveal") && isMatch && board && (
          <div className="card-pop p-4 sm:p-6">
            {phase === "question" ? (
              <TimerBar
                endsAt={state.endsAt}
                durationMs={state.secondsPerQuestion * 1000}
                serverNow={serverNow}
                label={
                  meRow?.submitted
                    ? `Locked in — ${submitted} of ${state.players.length} done`
                    : "Tap a person, then a dog"
                }
              />
            ) : (
              <div className="text-center font-display text-2xl font-black">
                {(meRow?.lastRoundCorrect ?? 0) > 0
                  ? `${meRow?.lastRoundCorrect} right — +${meRow?.lastAward}`
                  : "None right that time"}
              </div>
            )}

            <div className="mt-5">
              <MatchBoard
                board={board}
                claims={state.claims}
                meId={String(me.id)}
                answer={state.boardAnswer}
                pending={pending}
                disabled={phase === "reveal" || !!meRow?.submitted}
                onClaim={claim}
                onRelease={release}
              />
            </div>

            {phase === "question" && (
              <div className="mt-5 flex flex-col items-center gap-2">
                <button
                  onClick={() => send("submit")}
                  disabled={!!meRow?.submitted}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-8 py-3 disabled:opacity-50"
                >
                  {meRow?.submitted ? "Waiting for the others…" : "Lock it in →"}
                </button>
                <p className="text-center text-xs text-muted-foreground">
                  Change your mind as often as you like until you submit. Claiming early is worth
                  more — but nobody finds out who was right until the round ends.
                </p>
              </div>
            )}
          </div>
        )}

        {(phase === "question" || phase === "reveal") && !isMatch && question && (
          <div className="card-pop p-6">
            {phase === "question" ? (
              <TimerBar
                endsAt={state.endsAt}
                durationMs={state.secondsPerQuestion * 1000}
                serverNow={serverNow}
                label={picked === null ? "Pick a dog" : "Locked in — waiting for the others"}
              />
            ) : (
              <div className="text-center font-display text-2xl font-black">
                {state.answerIndex !== null && `The answer was ${OPTION_LABELS[state.answerIndex]}`}
              </div>
            )}

            <div className="mt-6">
              <QuestionPrompt>
                <HumanFace
                  seed={question.humanSeed}
                  url={question.humanUrl}
                  className="h-40 w-40 rounded-2xl border-2 border-[var(--ink)]"
                />
              </QuestionPrompt>
            </div>

            <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {question.options.map((dogIndex, i) => (
                <DogOption
                  key={`${question.itemId}-${i}`}
                  dogIndex={dogIndex}
                  label={OPTION_LABELS[i]}
                  disabled={phase === "reveal" || picked !== null}
                  state={
                    phase === "reveal"
                      ? i === state.answerIndex
                        ? "correct"
                        : i === picked
                          ? "wrong"
                          : "dimmed"
                      : i === picked
                        ? "picked"
                        : "idle"
                  }
                  onClick={() => answer(i)}
                />
              ))}
            </div>

            {phase === "question" && (
              <p className="text-center text-xs text-muted-foreground mt-4">
                {picked === null
                  ? "Faster answers score more — tap a dog or press 1–4."
                  : "Answer locked. No changing your mind."}
              </p>
            )}
          </div>
        )}

        {phase === "over" && (
          <div className="card-pop p-8">
            <Podium players={state.players} meId={String(me.id)} />
            <div className="mt-8 flex gap-3 justify-center flex-wrap">
              {isHost ? (
                <button
                  onClick={() => send("again")}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3"
                >
                  Play again →
                </button>
              ) : (
                <span className="text-muted-foreground font-bold self-center">
                  Waiting for the host to run it back…
                </span>
              )}
              {/* A button, not a Link: this is now the only way out of a
                  finished game, so it has to actually give up the seat rather
                  than leave the server holding it for the reconnect grace. */}
              <button onClick={leave} className="btn-pop btn-pop-hover bg-card px-6 py-3">
                Back to lobbies
              </button>
            </div>
          </div>
        )}

        {phase === "over" && state.leaderboard && (
          <Leaderboard
            entries={state.leaderboard}
            board={isMatch ? "multiplayer_match" : "multiplayer"}
            meId={String(me.id)}
            title={`🏅 Most wins — ${GAME_LABEL[state.gameType].toLowerCase()}`}
          />
        )}
      </div>

      <Scoreboard players={state.players} meId={String(me.id)} phase={state.phase} />
    </div>
  );
}

function Chooser({
  label,
  values,
  current,
  onPick,
}: {
  label: string;
  values: number[];
  current: number;
  onPick: (value: number) => void;
}) {
  return (
    <div>
      <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </div>
      <div className="flex gap-1">
        {values.map((v) => (
          <button
            key={v}
            onClick={() => onPick(v)}
            className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${
              v === current ? "bg-primary text-primary-foreground" : "bg-card"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
