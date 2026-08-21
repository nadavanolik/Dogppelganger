import { Outlet } from "react-router-dom";

import { AppSocketProvider } from "@/lib/appSocket";
import { AuthProvider } from "@/lib/auth";
import { UploadFeedProvider } from "@/lib/uploadFeed";

// Order matters: the socket needs a session to authenticate with, and the
// upload feed needs the socket to receive progress on. AuthProvider therefore
// has to be outermost.
export default function RootLayout() {
  return (
    <AuthProvider>
      <AppSocketProvider>
        <UploadFeedProvider>
          <Outlet />
        </UploadFeedProvider>
      </AppSocketProvider>
    </AuthProvider>
  );
}
