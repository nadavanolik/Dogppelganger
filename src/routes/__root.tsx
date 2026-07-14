import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/700.css";
import "@fontsource/fraunces/900.css";
import "@fontsource/nunito/500.css";
import "@fontsource/nunito/700.css";
import "@fontsource/nunito/900.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { StoreProvider } from "@/lib/store";
import { AppShell } from "@/components/AppShell";

function NotFoundComponent() {
  return (
    <AppShell>
      <div className="card-pop max-w-md mx-auto p-8 text-center">
        <div className="text-7xl mb-2">🐕‍🦺</div>
        <h1 className="font-display text-4xl font-black">Lost puppy</h1>
        <p className="mt-2 text-muted-foreground">This page ran off. Let's go home.</p>
        <Link to="/" className="btn-pop btn-pop-hover bg-primary text-primary-foreground inline-block mt-6 px-5 py-2">Back to home</Link>
      </div>
    </AppShell>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card-pop max-w-md p-8 text-center">
        <div className="text-6xl">🙀</div>
        <h1 className="font-display text-2xl font-bold mt-2">Something snapped</h1>
        <p className="mt-2 text-muted-foreground text-sm">{error.message}</p>
        <div className="mt-4 flex gap-2 justify-center">
          <button onClick={() => { router.invalidate(); reset(); }} className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2">Try again</button>
          <a href="/" className="btn-pop btn-pop-hover bg-card px-4 py-2">Home</a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "dogpelganger — find the dog you already are" },
      { name: "description", content: "Upload a photo, get the dog you'd be. Share it, chat with fellow pups, and play match games with the community." },
      { property: "og:title", content: "dogpelganger — find the dog you already are" },
      { property: "og:description", content: "Human → dog matching, a shared gallery, forums, DMs and multiplayer games. Pure playful chaos." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <StoreProvider>
        <Outlet />
      </StoreProvider>
    </QueryClientProvider>
  );
}
