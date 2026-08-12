import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, RequireAuth } from "@/components/AppShell";
import { DogOption, QuestionPrompt } from "@/components/game/DogOption";
import { HumanFace } from "@/components/game/HumanFace";
import { Leaderboard } from "@/components/game/Leaderboard";
import { LivesHearts, StatTile, StreakFlame } from "@/components/game/RunStats";
import { ApiError, gameApi, type LeaderEntry, type Question, type SoloResult } from "@/lib/gameApi";
import { useStore } from "@/lib/store";

export default Game;

/** How long the right answer stays on screen before the next question. */
const REVEAL_MS = 1200;

const OPTION_LABELS = ["A", "B"];

function Game() {
  return (
    <AppShell>
      <RequireAuth>
        <StreakSurvival />
      </RequireAuth>
    </AppShell>
  );
}

type Phase = "idle" | "playing" | "over";
type Stats = { lives: number; score: number; streak: number; longestStreak: number };

const NO_STATS: Stats = { lives: 3, score: 0, streak: 0, longestStreak: 0 };

function StreakSurvival() {
  const { state } = useStore();
  const me = state.user!;

  const [phase, setPhase] = useState<Phase>("idle");
  const [runToken, setRunToken] = useState<string | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [stats, setStats] = useState<Stats>(NO_STATS);
  const [reveal, setReveal] = useState<{ picked: number; answer: number } | null>(null);
  const [summary, setSummary] = useState<SoloResult | null>(null);
  const [board, setBoard] = useState<LeaderEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const loadBoard = useCallback(() => {
    gameApi
      .leaderboard("solo")
      .then((res) => setBoard(res.entries))
      .catch(() => setBoard([]));
  }, []);

  useEffect(loadBoard, [loadBoard]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const run = await gameApi.soloStart(me.id, me.username);
      setRunToken(run.runToken);
      setQuestion(run.question);
      setStats({
        lives: run.lives,
        score: run.score,
        streak: run.streak,
        longestStreak: run.longestStreak,
      });
      setReveal(null);
      setSummary(null);
      setPhase("playing");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start a run.");
    } finally {
      setBusy(false);
    }
  }, [me.id, me.username]);

  const pick = useCallback(
    async (choice: number) => {
      if (!runToken || !question || reveal || busy) return;
      setBusy(true);
      try {
        const result = await gameApi.soloAnswer(runToken, choice);
        setReveal({ picked: choice, answer: result.answerIndex });
        setStats({
          lives: result.lives,
          score: result.score,
          streak: result.streak,
          longestStreak: result.longestStreak,
        });

        // Hold the reveal, then either continue or wrap up the run.
        timer.current = window.setTimeout(() => {
          setReveal(null);
          if (result.over) {
            setSummary(result);
            setPhase("over");
            setQuestion(null);
            if (result.leaderboard) setBoard(result.leaderboard);
            else loadBoard();
          } else {
            setQuestion(result.question);
          }
        }, REVEAL_MS);
      } catch (err) {
        // A run that expired server-side (or a restarted backend) lands here.
        setError(err instanceof ApiError ? err.message : "That answer didn't register.");
        setPhase("idle");
        setRunToken(null);
        setQuestion(null);
      } finally {
        setBusy(false);
      }
    },
    [runToken, question, reveal, busy, loadBoard],
  );

  // 1 / 2 and the arrow keys, so a fast run doesn't depend on aim.
  useEffect(() => {
    if (phase !== "playing" || !question || reveal) return;
    const onKey = (e: KeyboardEvent) => {
      const index = { "1": 0, "2": 1, ArrowLeft: 0, ArrowRight: 1 }[e.key];
      if (index !== undefined) {
        e.preventDefault();
        void pick(index);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, question, reveal, pick]);

  const myBest = board.find((e) => e.playerId === me.id);

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start">
      <div className="space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-4xl md:text-5xl font-black">Streak survival</h1>
            <p className="text-muted-foreground">
              No clock. Three lives. Guess whose dog is whose for as long as you can.
            </p>
          </div>
          <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
            👥 Play with others →
          </Link>
        </header>

        {error && (
          <div className="card-pop-sm bg-destructive text-destructive-foreground p-3 text-sm font-bold">
            {error}
          </div>
        )}

        {phase === "playing" && question && (
          <div className="card-pop p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <LivesHearts lives={stats.lives} />
              <StreakFlame streak={stats.streak} />
              <div className="btn-pop bg-sunshine px-3 py-1">{stats.score} correct</div>
            </div>

            <div className="mt-6">
              <QuestionPrompt>
                <HumanFace
                  seed={question.humanSeed}
                  url={question.humanUrl}
                  className="h-44 w-44 rounded-2xl border-2 border-[var(--ink)]"
                />
              </QuestionPrompt>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-4 max-w-lg mx-auto">
              {question.options.map((dogIndex, i) => (
                <DogOption
                  key={`${question.itemId}-${i}`}
                  dogIndex={dogIndex}
                  label={OPTION_LABELS[i]}
                  disabled={!!reveal || busy}
                  state={
                    !reveal
                      ? "idle"
                      : i === reveal.answer
                        ? "correct"
                        : i === reveal.picked
                          ? "wrong"
                          : "dimmed"
                  }
                  onClick={() => void pick(i)}
                />
              ))}
            </div>

            <p className="text-center text-xs text-muted-foreground mt-4">
              {reveal
                ? reveal.picked === reveal.answer
                  ? "Correct! 🎉"
                  : "Nope — that's a life."
                : "Tap a dog, or press 1 / 2."}
            </p>
          </div>
        )}

        {phase === "idle" && (
          <div className="card-pop p-8 text-center">
            <div className="text-6xl">🐾</div>
            <h2 className="font-display text-3xl font-black mt-2">Ready?</h2>
            <p className="text-muted-foreground mt-1 max-w-md mx-auto">
              You'll see a human and two dogs. Pick the right double. Three wrong answers ends the
              run — your best goes on the board.
            </p>
            {myBest && (
              <div className="mt-4 flex justify-center gap-3">
                <StatTile label="your best" value={myBest.best} tint="bg-sunshine" />
                <StatTile label="longest streak" value={myBest.longestStreak} />
                <StatTile label="runs" value={myBest.gamesPlayed} />
              </div>
            )}
            <button
              onClick={() => void start()}
              disabled={busy}
              className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3 mt-6 text-lg disabled:opacity-50"
            >
              {busy ? "Dealing…" : "Start a run →"}
            </button>
          </div>
        )}

        {phase === "over" && summary && (
          <div className="card-pop p-8 text-center">
            <div className="text-6xl">{summary.score >= (myBest?.best ?? 0) ? "🏆" : "💀"}</div>
            <h2 className="font-display text-3xl font-black mt-2">Out of lives</h2>
            <div className="mt-4 flex justify-center gap-3 flex-wrap">
              <StatTile label="got right" value={summary.score} tint="bg-sunshine" />
              <StatTile label="longest streak" value={summary.longestStreak} />
              <StatTile label="rank" value={summary.rank ? `#${summary.rank}` : "—"} />
            </div>
            <div className="mt-6 flex gap-3 justify-center flex-wrap">
              <button
                onClick={() => void start()}
                disabled={busy}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3 disabled:opacity-50"
              >
                Go again →
              </button>
              <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-6 py-3">
                Race some friends
              </Link>
            </div>
          </div>
        )}
      </div>

      <Leaderboard
        entries={board}
        board="solo"
        meId={me.id}
        title="🏅 Best runs"
        empty="No runs yet. Yours could be first."
      />
    </div>
  );
}
