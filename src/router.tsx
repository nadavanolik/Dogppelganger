import { createBrowserRouter, Navigate } from "react-router-dom";

import RootLayout from "./RootLayout";
import ErrorPage from "./ErrorPage";
import NotFound from "./NotFound";
import { Protected, PublicOnly } from "./components/Guards";

import Index from "./routes/index";
import Gallery from "./routes/gallery";
import Game from "./routes/game";
import PlayHub from "./routes/play";
import UploadPage from "./routes/upload";
import Profile from "./routes/profile";
import Settings from "./routes/settings";
import NotifPage from "./routes/notifications";
import Login from "./routes/login";
import Signup from "./routes/signup";
import ForumList from "./routes/forum.index";
import NewPost from "./routes/forum.new";
import PostDetail from "./routes/forum.$id";
import Lobbies from "./routes/lobbies.index";
import Room from "./routes/lobbies.$id";
import Inbox from "./routes/messages.index";
import DM from "./routes/messages.$id";
import Result from "./routes/result.$id";

// Access is decided here, once, rather than page by page. Two layout routes
// wrap the two groups; anything outside them is genuinely public.
export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      // ---- public
      { index: true, element: <Index /> },
      // Browsable logged-out: the landing page shows a strip of it to visitors
      // who don't have an account yet.
      { path: "gallery", element: <Gallery /> },

      // ---- public *only* — already signed in? go to your profile
      {
        element: <PublicOnly />,
        children: [
          { path: "login", element: <Login /> },
          { path: "signup", element: <Signup /> },
        ],
      },

      // ---- everything else needs a session
      {
        element: <Protected />,
        children: [
          // /dashboard was a redirect-only route in the old app.
          { path: "dashboard", element: <Navigate to="/profile" replace /> },
          { path: "game", element: <Game /> },
          { path: "play", element: <PlayHub /> },
          { path: "upload", element: <UploadPage /> },
          { path: "profile", element: <Profile /> },
          { path: "settings", element: <Settings /> },
          { path: "notifications", element: <NotifPage /> },
          { path: "forum", element: <ForumList /> },
          { path: "forum/new", element: <NewPost /> },
          { path: "forum/:id", element: <PostDetail /> },
          { path: "lobbies", element: <Lobbies /> },
          { path: "lobbies/:id", element: <Room /> },
          { path: "messages", element: <Inbox /> },
          { path: "messages/:id", element: <DM /> },
          { path: "result/:id", element: <Result /> },
        ],
      },

      { path: "*", element: <NotFound /> },
    ],
  },
]);
