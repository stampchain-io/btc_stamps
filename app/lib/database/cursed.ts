import { Client } from "$mysql/mod.ts";
import { handleQuery, handleQueryWithClient } from './index.ts';
import { STAMP_TABLE } from "constants"

export const get_total_cursed = async () => {
  return await handleQuery(
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NULL
    AND is_reissue IS NULL;
    `,
    []
  );
};

export const get_total_cursed_with_client = async (client: Client) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NULL
    AND is_reissue IS NULL;
    `,
    []
  );
};

export const get_total_cursed_by_ident = async (ident: SUBPROTOCOLS) => {
  return await handleQuery(
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL;
    `,
    [ident]
  );
};

export const get_total_cursed_by_ident_with_client = async (client: Client, ident: SUBPROTOCOLS) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL;
    `,
    [ident]
  );
};

export const get_cursed_by_page = async (limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_cursed_by_page_with_client = async (client: Client, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_resumed_cursed_by_page_with_client = async (client: Client, limit = 1000, page = 1, order="DESC") => {
  order = order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT stamp, cpid, creator, creator_name, tx_hash, stamp_mimetype, supply, divisible, locked
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index ${order}
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_cursed_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE block_index = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    `,
    [block_index]
  );
};

export const get_cursed_by_block_index_with_client = async (client: Client, block_index: number) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE block_index = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    `,
    [block_index]
  );
};

export const get_cursed_by_ident = async (ident: SUBPROTOCOLS, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    LIMIT ? OFFSET ?;
    `,
    [ident, limit, offset]
  );
};

export const get_cursed_by_ident_with_client = async (client: Client, ident: SUBPROTOCOLS, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NULL
    AND is_reissue IS NULL
    ORDER BY tx_index
    LIMIT ? OFFSET ?;
    `,
    [ident, limit, offset]
  );
};

export const get_cursed_by_stamp = async (stamp: number) => {
  const issuances = await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp]
  );
};