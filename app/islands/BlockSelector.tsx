import type { Signal } from "@preact/signals";
import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

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

  const isSelected = selected.value === block;

  return (
    <a
      href={`/block/${block.block_index}`}
      class={`${
        isSelected
          ? "bg-white text-gray-700"
          : "bg-gray-700 text-white"
      } shadow-md outline-none focus:outline-none active:outline-none rounded overflow-hidden transition transform hover:shadow-lg sm:rounded-lg`}
      onclick={handleClick}
    >
      <div class="text-center font-semibold p-1 text-xs sm:text-lg">
        <p>{block.block_index}</p>
        <p class="font-normal text-xs">{short_address(block.block_hash)}</p>
      </div>
      <div class="text-center text-xs p-1 sm:text-sm">
        {dayjs(Number(block.block_time) * 1000).fromNow()}
      </div>
    </a>
  );
}


