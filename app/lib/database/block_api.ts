import {
  connectDb,
  get_block_info_with_client,
  get_issuances_by_block_index_with_client,
  get_last_block_with_client,
} from "./index.ts";

export async function api_get_block_with_issuances(block_index: number) {
  try {
    const client = await connectDb();
    if (!client) {
      throw new Error("Could not connect to database");
    }
    const block_info = await get_block_info_with_client(client, block_index);
    if (!block_info || !block_info?.rows?.length) {
      throw new Error(`Block: ${block_index} not found`);
    }
    const last_block = await get_last_block_with_client(client);
    if (!last_block || !last_block?.rows?.length) {
      throw new Error("Could not get last block");
    }
    const data = await get_issuances_by_block_index_with_client(
      client,
      block_index,
    );
    const response = {
      block_info: block_info.rows[0],
      data: data.rows,
      last_block: last_block.rows[0]["last_block"],
    };
    client.close();
    return response;
  } catch (error) {
    console.error(error);
    throw error;
  }
}
