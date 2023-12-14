import {
  connectDb,
  get_stamps_by_page_with_client,
  get_resumed_stamps_by_page_with_client,
  get_total_stamps_with_client,
} from "$lib/database/index.ts";

export async function api_get_stamps(page: number=0, page_size: number=1000, order: "DESC"|"ASC"="DESC") {
  try {
    const client = await connectDb();
    const stamps = await get_resumed_stamps_by_page_with_client(client, page_size, page, order);
    if (!stamps) {
      throw new Error("No stamps found");
    }
    const total = await get_total_stamps_with_client(client);;
    return {
      stamps: stamps.rows,
      total: total.rows[0].total,
      pages: Math.ceil(total.rows[0].total / page_size),
      page: page,
      page_size: page_size,
    };
  } catch (error) {
    console.error(error);
    throw error;
  }
}