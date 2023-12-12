import {
  connectDb,
  get_block_info_with_client,
  get_issuances_by_block_index_with_client,
  get_sends_by_block_index_with_client,
  get_last_block_with_client,
  get_related_blocks_with_client,
} from "$lib/database/index.ts";

export async function api_get_block(block_index: number) {
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
    const issuances = await get_issuances_by_block_index_with_client(
      client,
      block_index,
    );

    const sends = await get_sends_by_block_index_with_client(
      client,
      block_index,
    );
    const response = {
      block_info: block_info.rows[0],
      issuances: issuances.rows,
      sends: sends.rows,
      last_block: last_block.rows[0]["last_block"],
    };
    client.close();
    return response;
  } catch (error) {
    console.error(error);
    throw error;
  }
}

export const api_get_related_blocks = async (block_index: number) => {
  try {
    const client = await connectDb();
    if (!client) {
      throw new Error("Could not connect to database");
    }
    const blocks = await get_related_blocks_with_client(client, block_index);
    const last_block = await get_last_block_with_client(client);
    if (!last_block || !last_block?.rows?.length) {
      throw new Error("Could not get last block");
    }
    const response = {
      blocks,
      last_block: last_block.rows[0]["last_block"],
    };
    client.close();
    return response;
  } catch (error) {
    console.error(error);
    throw error;
  }
};

export const api_get_last_block = async () => {
  try {
    const client = await connectDb();
    if (!client) {
      throw new Error("Could not connect to database");
    }
    const last_block = await get_last_block_with_client(client);
    if (!last_block || !last_block?.rows?.length) {
      throw new Error("Could not get last block");
    }
    const response = {
      last_block: last_block.rows[0]["last_block"],
    };
    client.close();
    return response;
  } catch (error) {
    console.error(error);
    throw error;
  }
};
