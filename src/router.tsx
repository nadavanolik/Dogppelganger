import { createBrowserRouter, Navigate } from "react-router-dom";

import RootLayout from "./RootLayout";
import ErrorPage from "./ErrorPage";
import NotFound from "./NotFound";

import Index from "./routes/index";
import Gallery from "./routes/gallery";
import Game from "./routes/game";
import PlayHub from "./routes/play";
import UploadPage from "./routes/upload";
import Profile from "./routes/profile";
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

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <Index /> },
      // /dashboard was a redirect-only route in the old app.
      { path: "dashboard", element: <Navigate to="/profile" replace /> },
      { path: "gallery", element: <Gallery /> },
      { path: "game", element: <Game /> },
      { path: "play", element: <PlayHub /> },
      { path: "upload", element: <UploadPage /> },
      { path: "profile", element: <Profile /> },
      { path: "notifications", element: <NotifPage /> },
      { path: "login", element: <Login /> },
      { path: "signup", element: <Signup /> },
      { path: "forum", element: <ForumList /> },
      { path: "forum/new", element: <NewPost /> },
      { path: "forum/:id", element: <PostDetail /> },
      { path: "lobbies", element: <Lobbies /> },
      { path: "lobbies/:id", element: <Room /> },
      { path: "messages", element: <Inbox /> },
      { path: "messages/:id", element: <DM /> },
      { path: "result/:id", element: <Result /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
