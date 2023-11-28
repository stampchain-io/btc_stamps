import { HandlerContext, Handlers, Request, PageProps } from "$fresh/server.ts";
import { Partial } from "$fresh/runtime.ts";
import {
  get_last_x_blocks_with_client,
  connectDb,
} from "$lib/database/index.ts";
import Block from "$islands/BlockSelector.tsx";
import BlockInfo from "$islands/BlockInfo.tsx";


export default function Home(/*props: PageProps<BlockRow[]>*/) {

  return (

    <div class="px-4 py-8 mx-auto bg-[#000000]">
      <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>
      <div class="grid grid-cols-1 gap-4 mt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <Block />
      </div>

      {/*  <BlockInfo block={selected} /> */}

    </div>

  );
}
