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

export async function api_get_stamp(id: string) {
  try {
    const client = await connectDb();
    const stamp = await get_stamp_with_client(client, id);
    if (!stamp) {
      throw new Error(`Error: Stamp ${id} not found`);
    }
    const total = await get_total_stamps_with_client(client);
    const cpid_result = await get_cpid_from_identifier_with_client(client, id);
    const cpid = cpid_result.rows[0].cpid;
    const holders = await get_holders(cpid);
    return {
      stamp: stamp,
      holders: holders.map((holder: any) => {
        return {
          address: holder.address,
          quantity: holder.divisible ? holder.quantity / 100000000 : holder.quantity,
        }
      }),
      total: total.rows[0].total
    };
  } catch (error) {
    console.error(error);
    return null;
  }
}