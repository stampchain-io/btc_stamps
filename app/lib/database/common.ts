import { Client } from "$mysql/mod.ts";
import { handleQuery, handleQueryWithClient } from "./index.ts";

export const get_block_info = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM blocks
    WHERE block_index = ?;
    `,
    [block_index],
  );
};

export const get_block_info_with_client = async (
  client: Client,
  block_index: number,
) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM blocks
    WHERE block_index = ?;
    `,
    [block_index],
  );
};

export const get_last_block = async () => {
  return await handleQuery(
    `
    SELECT MAX(block_index)
    AS last_block
    FROM blocks;
    `,
    [],
  );
};

export const get_last_block_with_client = async (client: Client) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT MAX(block_index)
    AS last_block
    FROM blocks;
    `,
    [],
  );
};

export const get_last_x_blocks = async (num = 10) => {
  const blocks = await handleQuery(
    `
    SELECT * FROM blocks
    ORDER BY block_index DESC
    LIMIT ?;
    `,
    [num],
  );
  const populated = blocks.rows.map(async (block) => {
    const tx_info_from_block = await handleQuery(
      `
      SELECT COUNT(*) AS tx_count
      FROM StampTableV4
      WHERE block_index = ?;
      `,
      [block.block_index],
    );
    return {
      ...block,
      tx_count: tx_info_from_block.rows[0]["tx_count"],
    };
  });

  return Promise.all(populated.reverse());
};

export const get_last_x_blocks_with_client = async (
  client: Client,
  num = 10,
) => {
  const blocks = await handleQueryWithClient(
    client,
    `
    SELECT * FROM blocks
    ORDER BY block_index DESC
    LIMIT ?;
    `,
    [num],
  );
  const populated = blocks.rows.map(async (block) => {
    const tx_info_from_block = await handleQueryWithClient(
      client,
      `
      SELECT COUNT(*) AS tx_count
      FROM StampTableV4
      WHERE block_index = ?;
      `,
      [block.block_index],
    );

    return {
      ...block,
      tx_count: tx_info_from_block.rows[0]["tx_count"],
    };
  });
  return Promise.all(populated.reverse());
};

export const get_related_blocks = async (
  block_index: number,
) => {
  const blocks = await handleQuery(
    `
    SELECT * FROM blocks
    WHERE block_index >= ? - 2
    AND block_index <= ? + 2
    ORDER BY block_index DESC;
    `,
    [block_index, block_index],
  );
  const populated = blocks?.rows?.map(async (block) => {
    const tx_info_from_block = await handleQuery(
      `
      SELECT COUNT(*) AS tx_count
      FROM StampTableV4
      WHERE block_index = ?;
      `,
      [block.block_index],
    );

    return {
      ...block,
      tx_count: tx_info_from_block.rows[0]["tx_count"] ?? 0,
    };
  });

  return Promise.all(populated.reverse());
};

export const get_related_blocks_with_client = async (
  client: Client,
  block_index: number,
) => {
  const blocks = await handleQueryWithClient(
    client,
    `
    SELECT * FROM blocks
    WHERE block_index >= ? - 2
    AND block_index <= ? + 2
    ORDER BY block_index DESC;
    `,
    [block_index, block_index],
  );
  const populated = blocks?.rows?.map(async (block) => {
    const tx_info_from_block = await handleQueryWithClient(
      client,
      `
      SELECT COUNT(*) AS tx_count
      FROM StampTableV4
      WHERE block_index = ?;
      `,
      [block.block_index],
    );
    return {
      ...block,
      tx_count: tx_info_from_block.rows[0]["tx_count"] ?? 0,
    };
  });
  const result = await Promise.all(populated.reverse());
  return result;
};

export const get_issuances_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM StampTableV4
    WHERE block_index = ?
    ORDER BY tx_index;
    `,
    [block_index],
  );
};

export const get_issuances_by_block_index_with_client = async (
  client: Client,
  block_index: number,
) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM StampTableV4
    WHERE block_index = ?
    ORDER BY tx_index;
    `,
    [block_index],
  );
};

export const get_sends_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM sends
    WHERE block_index = ?
    ORDER BY tx_index;
    `,
    [block_index],
  );
};

export const get_sends_by_block_index_with_client = async (
  client: Client,
  block_index: number,
) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM sends
    WHERE block_index = ?
    ORDER BY tx_index;
    `,
    [block_index],
  );
};

export const get_issuances_by_stamp = async (stamp: number) => {
  let issuances = await handleQuery(
    `
    SELECT * FROM StampTableV4
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQuery(
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ?)
    ORDER BY tx_index;
    `,
    [cpid],
  );
  return issuances;
};

export const get_issuances_by_stamp_with_client = async (
  client: Client,
  stamp: number,
) => {
  let issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM StampTableV4
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ?)
    ORDER BY tx_index;
    `,
    [cpid],
  );
  return issuances;
};

export const get_issuances_by_identifier = async (identifier: string) => {
  let issuances = await handleQuery(
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?)
    ORDER BY tx_index;
    `,
    [identifier, identifier, identifier],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQuery(
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ?)
    ORDER BY tx_index;
    `,
    [cpid],
  );
  return issuances;
};

export const get_issuances_by_identifier_with_client = async (
  client: Client,
  identifier: string,
) => {
  let issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?)
    ORDER BY tx_index;
    `,
    [identifier, identifier, identifier],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM StampTableV4
    WHERE (cpid = ?)
    ORDER BY tx_index;
    `,
    [cpid],
  );
  return issuances;
};
