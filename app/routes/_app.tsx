import { AppProps } from "$fresh/server.ts";

export default function App({ Component }: AppProps) {
  return (
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>app</title>
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body class="bg-black">
      <div class="px-2 py-8 mx-auto bg-[#000000] flex flex-col md:gap-4 overflow-auto max-w-6xl">
        <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>
        <Component />
      </div>
      </body>
    </html>
  );
}
