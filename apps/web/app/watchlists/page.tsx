import { redirect } from "next/navigation";

export default function WatchlistsCompatibilityPage() {
  redirect("/settings#monitored-channels");
}
