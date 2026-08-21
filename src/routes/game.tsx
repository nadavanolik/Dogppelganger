import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { DogOption, QuestionPrompt } from "@/components/game/DogOption";
import { HumanFace } from "@/components/game/HumanFace";
import { Leaderboard } from "@/components/game/Leaderboard";
import { MatchBoard } from "@/components/game/MatchBoard";
import { LivesHearts, StatTile, StreakFlame } from "@/components/game/RunStats";
import {
  ApiError,
  gameApi,
  type GameType,
  type LeaderEntry,
  type MatchBoard as BoardData,
  type PairMap,
  type Question,
  type SoloMatchResult,
  type SoloResult,
} from "@/lib/gameApi";
import { useAuth } from "@/lib/auth";

export default Game;

/** How long the right answer stays on screen before the next question. */
const REVEAL_MS = 1200;
/** Longer for a board: there are four verdicts to take in, not one. */
const BOARD_REVEAL_MS = 2800;

const OPTION_LABELS = ["A", "B"];

/**
 * Which game you're playing is chosen once, up front — not from a switch that
 * sits above the board. With a toggle there you can walk out of a run halfway
 * through by clicking the other game, which leaves the run unfinished and reads
 * as a glitch. Here the choice is a screen you leave behind.
 */
function Game() {
  const [chosen, setChosen] = useState<GameType | null>(null);
  const back = () => setChosen(null);

  return (
    <AppShell>
      {chosen === null ? (
        <GamePicker onPick={setChosen} />
      ) : chosen === "match" ? (
        <MixAndMatch onBack={back} />
      ) : (
        <StreakSurvival onBack={back} />
      )}
    </AppShell>
  );
}

function GamePicker({ onPick }: { onPick: (game: GameType) => void }) {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <header className="text-center">
        <h1 className="font-display text-5xl md:text-6xl font-black">Single player</h1>
        <p className="text-muted-foreground mt-2">
          Two games, three lives each, no clock in either. Pick one.
        </p>
      </header>

      <div className="grid md:grid-cols-2 gap-6">
        <button
          onClick={() => onPick("match")}
          className="card-pop p-8 hover:-translate-y-1 transition block text-left"
        >
          <div className="text-7xl">🔗</div>
          <div className="mt-4 font-display text-3xl font-black">Mix &amp; match</div>
          <p className="text-muted-foreground mt-1">
            Four people, four dogs. Link them all up and submit. Get the whole board right and it
            costs you nothing; miss any of it and it's a life.
          </p>
          <span className="mt-4 inline-block btn-pop bg-sunshine px-4 py-2 text-sm">
            Deal a board →
          </span>
        </button>

        <button
          onClick={() => onPick("double")}
          className="card-pop p-8 hover:-translate-y-1 transition block text-left"
        >
          <div className="text-7xl">🎯</div>
          <div className="mt-4 font-display text-3xl font-black">Streak survival</div>
          <p className="text-muted-foreground mt-1">
            One person, two dogs, over and over. Keep picking the right double and see how far you
            get before three wrong answers end it.
          </p>
          <span className="mt-4 inline-block btn-pop bg-sunshine px-4 py-2 text-sm">
            Start a run →
          </span>
        </button>
      </div>

      <p className="text-center">
        <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-5 py-2 inline-block">
          👥 Play these with other people →
        </Link>
      </p>
    </div>
  );
}

type Phase = "idle" | "playing" | "over";
type Stats = { lives: number; score: number; streak: number; longestStreak: number };

const NO_STATS: Stats = { lives: 3, score: 0, streak: 0, longestStreak: 0 };

function StreakSurvival({ onBack }: { onBack: () => void }) {
  const { user } = useAuth();
  const me = user!;

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
      const run = await gameApi.soloStart();
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
  }, []);

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

  const myBest = board.find((e) => e.playerId === String(me.id));

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
          <div className="flex gap-2">
            {/* Deliberately absent mid-run: leaving is finishing or losing. */}
            {phase !== "playing" && (
              <button onClick={onBack} className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
                ← Other games
              </button>
            )}
            <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
              👥 Play with others →
            </Link>
          </div>
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
        meId={String(me.id)}
        title="🏅 Best runs"
        empty="No runs yet. Yours could be first."
      />
    </div>
  );
}

/**
 * Solo Mix & Match: board after board, three lives, no clock.
 *
 * The same `MatchBoard` the multiplayer room uses — here you're simply the only
 * player claiming anything, so your pairings are the only lines on it. Nothing
 * is marked until you submit, which is what stops it becoming a game of poking
 * tiles until one lights up.
 */
function MixAndMatch({ onBack }: { onBack: () => void }) {
  const { user } = useAuth();
  const me = user!;

  const [phase, setPhase] = useState<Phase>("idle");
  const [runToken, setRunToken] = useState<string | null>(null);
  const [board, setBoard] = useState<BoardData | null>(null);
  const [pairs, setPairs] = useState<Record<number, number>>({});
  const [answer, setAnswer] = useState<PairMap | null>(null);
  const [stats, setStats] = useState<Stats>(NO_STATS);
  const [summary, setSummary] = useState<SoloMatchResult | null>(null);
  const [table, setTable] = useState<LeaderEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const loadTable = useCallback(() => {
    gameApi
      .leaderboard("solo_match")
      .then((res) => setTable(res.entries))
      .catch(() => setTable([]));
  }, []);

  useEffect(loadTable, [loadTable]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const run = await gameApi.soloMatchStart();
      setRunToken(run.runToken);
      setBoard(run.board);
      setPairs({});
      setAnswer(null);
      setStats({
        lives: run.lives,
        score: run.score,
        streak: run.streak,
        longestStreak: run.longestStreak,
      });
      setSummary(null);
      setPhase("playing");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start a run.");
    } finally {
      setBusy(false);
    }
  }, []);

  // A human takes one dog and a dog takes one human, so a new pairing displaces
  // whatever it collides with — the local echo of the room's exclusive claims.
  const claim = useCallback((human: number, dog: number) => {
    setPairs((current) => {
      const next: Record<number, number> = {};
      for (const [slot, taken] of Object.entries(current)) {
        if (taken !== dog && Number(slot) !== human) next[Number(slot)] = taken;
      }
      next[human] = dog;
      return next;
    });
  }, []);

  const release = useCallback((human: number) => {
    setPairs((current) => {
      const next = { ...current };
      delete next[human];
      return next;
    });
  }, []);

  const submit = useCallback(async () => {
    if (!runToken || !board || answer || busy) return;
    setBusy(true);
    try {
      const asPairs: PairMap = {};
      for (const [human, dog] of Object.entries(pairs)) asPairs[human] = dog;
      const result = await gameApi.soloMatchSubmit(runToken, asPairs);

      setAnswer(result.boardAnswer);
      setStats({
        lives: result.lives,
        score: result.score,
        streak: result.streak,
        longestStreak: result.longestStreak,
      });

      // Hold the marked board, then either deal the next one or wrap up.
      timer.current = window.setTimeout(() => {
        setAnswer(null);
        setPairs({});
        if (result.over) {
          setSummary(result);
          setPhase("over");
          setBoard(null);
          if (result.leaderboard) setTable(result.leaderboard);
          else loadTable();
        } else {
          setBoard(result.board);
        }
      }, BOARD_REVEAL_MS);
    } catch (err) {
      // A run that expired server-side (or a restarted backend) lands here.
      setError(err instanceof ApiError ? err.message : "That board didn't register.");
      setPhase("idle");
      setRunToken(null);
      setBoard(null);
    } finally {
      setBusy(false);
    }
  }, [runToken, board, answer, busy, pairs, loadTable]);

  // Enter submits, so a finished board doesn't need a trip to the button.
  useEffect(() => {
    if (phase !== "playing" || answer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      void submit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, answer, submit]);

  const myBest = table.find((e) => e.playerId === String(me.id));
  const paired = Object.keys(pairs).length;
  const rightThisBoard = answer
    ? Object.entries(pairs).filter(([human, dog]) => answer[human] === dog).length
    : 0;

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start">
      <div className="space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-4xl md:text-5xl font-black">Mix &amp; match</h1>
            <p className="text-muted-foreground">
              Four people, four dogs, no clock. Link them all up before you submit.
            </p>
          </div>
          <div className="flex gap-2">
            {/* Deliberately absent mid-run: leaving is finishing or losing. */}
            {phase !== "playing" && (
              <button onClick={onBack} className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
                ← Other games
              </button>
            )}
            <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
              👥 Race some friends →
            </Link>
          </div>
        </header>

        {error && (
          <div className="card-pop-sm bg-destructive text-destructive-foreground p-3 text-sm font-bold">
            {error}
          </div>
        )}

        {phase === "playing" && board && (
          <div className="card-pop p-4 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <LivesHearts lives={stats.lives} />
              <StreakFlame streak={stats.streak} />
              <div className="btn-pop bg-sunshine px-3 py-1">{stats.score} pairs</div>
            </div>

            <div className="mt-5">
              <MatchBoard
                board={board}
                claims={Object.entries(pairs).map(([human, dog]) => ({
                  human: Number(human),
                  dog,
                  playerId: String(me.id),
                  name: me.username,
                }))}
                meId={String(me.id)}
                answer={answer}
                disabled={!!answer || busy}
                onClaim={claim}
                onRelease={release}
              />
            </div>

            <div className="mt-5 flex flex-col items-center gap-2">
              <button
                onClick={() => void submit()}
                disabled={!!answer || busy || paired === 0}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-8 py-3 disabled:opacity-50"
              >
                {answer ? "Marking…" : `Submit ${paired} of 4 →`}
              </button>
              <p className="text-center text-xs text-muted-foreground">
                {answer
                  ? rightThisBoard === 4
                    ? "All four. 🎉"
                    : `${rightThisBoard} right — that's a life.`
                  : "Tap a person, then a dog. Change your mind as often as you like — a board is only marked once you submit."}
              </p>
            </div>
          </div>
        )}

        {phase === "idle" && (
          <div className="card-pop p-8 text-center">
            <div className="text-6xl">🔗</div>
            <h2 className="font-display text-3xl font-black mt-2">Ready?</h2>
            <p className="text-muted-foreground mt-1 max-w-md mx-auto">
              Four people and their four dogs, shuffled. Get the whole board right and it costs you
              nothing; miss any of it and it's a life. Three lives, no clock.
            </p>
            {myBest && (
              <div className="mt-4 flex justify-center gap-3">
                <StatTile label="your best" value={myBest.best} tint="bg-sunshine" />
                <StatTile label="perfect boards" value={myBest.longestStreak} />
                <StatTile label="runs" value={myBest.gamesPlayed} />
              </div>
            )}
            <button
              onClick={() => void start()}
              disabled={busy}
              className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3 mt-6 text-lg disabled:opacity-50"
            >
              {busy ? "Dealing…" : "Deal a board →"}
            </button>
          </div>
        )}

        {phase === "over" && summary && (
          <div className="card-pop p-8 text-center">
            <div className="text-6xl">{summary.score >= (myBest?.best ?? 0) ? "🏆" : "💀"}</div>
            <h2 className="font-display text-3xl font-black mt-2">Out of lives</h2>
            <div className="mt-4 flex justify-center gap-3 flex-wrap">
              <StatTile label="pairs matched" value={summary.score} tint="bg-sunshine" />
              <StatTile label="perfect boards" value={summary.longestStreak} />
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
        entries={table}
        board="solo_match"
        meId={String(me.id)}
        title="🏅 Most pairs"
        empty="No runs yet. Yours could be first."
      />
    </div>
  );
}
