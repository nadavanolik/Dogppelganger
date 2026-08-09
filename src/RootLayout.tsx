import { Outlet } from "react-router-dom";
import { StoreProvider } from "@/lib/store";

// Wraps every page with the app-wide store and renders the matched route.
export default function RootLayout() {
  return (
    <StoreProvider>
      <Outlet />
    </StoreProvider>
  );
}
