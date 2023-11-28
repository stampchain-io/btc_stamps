import { signal } from "@preact/signals";
import type { Signal } from "@preact/signals";
import { API_BASE_URL } from "$lib/utils/index.ts";

console.log('API_BASE_URL:', API_BASE_URL);

export const blocksSignal: Signal<BlockRow[]> = signal([]);
export const blockSelected: Signal<BlockRow> = signal(null);


export async function fetchBlocks() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v2/block/block_count/4`);
    if (response.ok) {
      const newBlocks = await response.json();
      console.log('Fetched blocks:', newBlocks);
      blocksSignal.value = newBlocks;
      if (!blockSelected.value){
        blockSelected.value = newBlocks[0];
      }
    } else {
      throw new Error('Failed to fetch blocks');
    }
  } catch (error) {
    console.error('Error fetching blocks:', error);
  }
}
