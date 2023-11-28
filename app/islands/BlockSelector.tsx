import type { Signal } from "@preact/signals";
import { Head } from "$fresh/runtime.ts"
import { useEffect, useState } from "preact/hooks";
import { blockSelected, blocksSignal, fetchBlocks } from "$lib/store/index.ts";

export default function BlockSelector() {
  function handleClick() {
    console.log(`clicked: ${block.block_index}`);
    blockSelected.value = block;
  }

  const [isUpdating, setIsUpdating] = useState(false);
  useEffect(() => {
    fetchBlocks();
    const interval = setInterval(() => {
      setIsUpdating(true);
      fetchBlocks();
      setTimeout(() => setIsUpdating(false), 500); // Ajusta la duración según tu animación
    }, 10000);
    return () => {
      clearInterval(interval);
      console.log("BlockSelector: useEffect cleanup");
    }
  }, []);

  return (
    blocksSignal.value.map((block) => (
      <>
        <Head>
          <link rel="stylesheet" href="styles/BlockSelector.styles.css" />
        </Head>
        <button
          onClick={handleClick}
          class={`p-4 bg-[#ffffff] rounded-lg shadow outline-none focus:outline-none active:outline-none ${blockSelected.value === block ? "border-4 border-[#000000] bg-[#fefefefe]" : ""} ${isUpdating ? "sliding-exit" : "sliding-enter"} slide-and-fade`}
        >
          <div class="text-xl text-center text-[#000000]">{block.block_index}</div>
          <div class="text-center text-[#000000] py-2 text-lg">
            {
              `${block.block_hash.substring(0, 10)}...${block.block_hash.substring(block.block_hash.length - 10, block.block_hash.length)}`
            }
          </div>
          <div class="text-center text-[#000000] text-lg">
            stamps: {
              block.tx_count
            }
          </div>
        </button>
      </>
    )
    ));
}
