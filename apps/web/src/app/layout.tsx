import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Digital Twin",
  description: "A private, interpretable decision-support twin.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
