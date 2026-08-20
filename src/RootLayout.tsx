import { Outlet } from "react-router-dom";
import { StoreProvider } from "@/lib/store";
import { UploadFeedProvider } from "@/lib/uploadFeed";

// Wraps every page with the app-wide store and renders the matched route.
export default function RootLayout() {
  return (
    <StoreProvider>
      <UploadFeedProvider>
        <Outlet />
      </UploadFeedProvider>
    </StoreProvider>
  );
}
