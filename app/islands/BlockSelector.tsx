import type { Signal } from "@preact/signals";
import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

interface BlockProps {
  block: BlockRow;
  selected: Signal<BlockRow>;
}

export default function Block(props: BlockProps) {
  const { block, selected } = props;
  function handleClick() {
    selected.value = block;
  }

  return (
    <a
      href={`/block/${block.block_index}`}
      class={`bg-gray-700 shadow outline-none focus:outline-none active:outline-none ${
        selected.value === block
          ? "border-4 border-[#000000] bg-[#fefefefe] text-gray-700"
          : "text-[#fefefefe]"
      }`}
    >
      <div class="text-center text-[#000000]">{block.block_index}</div>
      <div class="text-center text-[#000000]">
        {dayjs(Number(block.block_time) * 1000).fromNow()}
      </div>
      <div class="text-center text-[#000000] text-lg">
        issuances: {block.tx_count}
      </div>
    </a>
  );
}
