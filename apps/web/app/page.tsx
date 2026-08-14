import type { Metadata } from "next";

import { LandingPage } from "@/components/landing/landing-page";

export const metadata: Metadata = {
  title: "EarlySignal — Know what to publish before the trend gets obvious",
  description:
    "Evidence-backed emerging YouTube topics, ranked for your AI or technology channel with timing, content gaps and source links.",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "EarlySignal — Creator Trend Intelligence",
    description:
      "Find narrow, rising YouTube topics that fit your channel before they become obvious.",
    type: "website",
  },
};

export default function Home() {
  return <LandingPage />;
}
