import type { Signal } from "@preact/signals";

interface BlockProps {
  block: BlockRow;
  selected: Signal<BlockRow>;
}

export default function Block(props: CounterProps) {
  const { block, selected } = props;
  function handleClick () {
    console.log(`clicked: ${block.block_index}`);
    selected.value = block;
  }

  return (
    <button
      onClick={handleClick}
      class={`p-4 bg-[#ffffff] rounded-lg shadow outline-none focus:outline-none active:outline-none ${selected.value === block ? "border-4 border-[#000000] bg-[#fefefefe]" : ""}`}
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
  );
}
