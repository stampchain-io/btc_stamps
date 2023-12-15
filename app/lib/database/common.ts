import { Client } from "$mysql/mod.ts";
import { handleQuery, handleQueryWithClient, summarize_issuances } from "./index.ts";
import { STAMP_TABLE, SEND_TABLE, BLOCK_TABLE } from "constants"
import { get_balances } from "utils/xcp.ts"

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
      FROM ${STAMP_TABLE}
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
      FROM ${STAMP_TABLE}
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
      FROM ${STAMP_TABLE}
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
    const issuances_from_block = await handleQueryWithClient(
      client,
      `
      SELECT COUNT(*) AS issuances
      FROM ${STAMP_TABLE}
      WHERE block_index = ?;
      `,
      [block.block_index],
    );

    const sends_from_block = await handleQueryWithClient(
      client,
      `
      SELECT COUNT(*) AS sends
      FROM sends
      WHERE block_index = ?;
      `,
      [block.block_index],
    );

    return {
      ...block,
      issuances: issuances_from_block.rows[0]["issuances"] ?? 0,
      sends: sends_from_block.rows[0]["sends"] ?? 0,
    };
  });
  const result = await Promise.all(populated.reverse());
  return result;
};

export const get_issuances_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE block_index = ?
    ORDER BY tx_index;
    `,
    [block_index],
  );
};

// export const get_issuances_by_block_index_with_client = async (
//   client: Client,
//   block_index: number,
// ) => {
//   return await handleQueryWithClient(
//     client,
//     `
//     SELECT * FROM ${STAMP_TABLE}
//     WHERE block_index = ?
//     ORDER BY tx_index;
//     `,
//     [block_index],
//   );
// };

export const get_issuances_by_block_index_with_client = async (
  client: Client,
  block_index: number,
) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT st.*, num.stamp AS stamp, num.is_btc_stamp AS is_btc_stamp
    FROM ${STAMP_TABLE} st
    LEFT JOIN (
        SELECT cpid, stamp, is_btc_stamp
        FROM ${STAMP_TABLE}
        WHERE stamp IS NOT NULL
        AND is_btc_stamp IS NOT NULL
    ) num ON st.cpid = num.cpid
    WHERE st.block_index = ?
    ORDER BY st.tx_index;
    `,
    [block_index],
  );
};



export const get_sends_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT s.*, st.*
    FROM sends s
    JOIN ${STAMP_TABLE} st ON s.cpid = st.cpid
    WHERE s.block_index = ?
      AND st.is_valid_base64 = true
      AND st.block_index = (SELECT MIN(block_index) 
                            FROM ${STAMP_TABLE} 
                            WHERE cpid = s.cpid 
                              AND is_valid_base64 = 1)
    ORDER BY s.tx_index;
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
    SELECT s.*, st.*
    FROM sends s
    JOIN ${STAMP_TABLE} st ON s.cpid = st.cpid
    WHERE s.block_index = ?
      AND st.is_valid_base64 = true
      AND st.block_index = (SELECT MIN(block_index) 
                            FROM ${STAMP_TABLE} 
                            WHERE cpid = s.cpid 
                              AND is_valid_base64 = 1)
    ORDER BY s.tx_index;
    `,
    [block_index],
  );
};

export const get_issuances_by_stamp = async (stamp: number) => {
  let issuances = await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
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
    SELECT * FROM ${STAMP_TABLE}
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp],
  );
  const cpid = issuances?.rows[0]?.cpid;
  if (!cpid) return null;
  issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
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
    SELECT * FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?)
    ORDER BY tx_index;
    `,
    [identifier, identifier, identifier],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
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
    SELECT * FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?)
    ORDER BY tx_index;
    `,
    [identifier, identifier, identifier],
  );
  const cpid = issuances.rows[0].cpid;
  issuances = await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE (cpid = ?)
    ORDER BY tx_index;
    `,
    [cpid],
  );
  return issuances;
};

export const get_balances_by_address = async (address: string) => {
  try {
    const xcp_balances = await get_balances(address);
    const assets = xcp_balances.map(balance => balance.asset);

    const query = `SELECT * FROM ${STAMP_TABLE} WHERE cpid IN (${assets.map(() => `?`).join(',')})`;
    const balances = await handleQuery(query, assets);

    const grouped = balances.rows.reduce((acc, cur) => {
      acc[cur.cpid] = acc[cur.cpid] || [];
      acc[cur.cpid].push(cur);
      return acc;
    }, {});

    const summarized = Object.keys(grouped).map(key => summarize_issuances(grouped[key]));

    return summarized.map(summary => {
      const xcp_balance = xcp_balances.find(balance => balance.asset === summary.cpid);
      return {
        ...summary,
        balance: xcp_balance ? xcp_balance.quantity : 0,
      };
    });
  } catch (error) {
    console.error("Error al obtener balances:", error);
    return [];
  }
};

export const get_balances_by_address_with_client = async (
  client: Client,
  address: string
) => {
  try {
    const xcp_balances = await get_balances(address);
    const assets = xcp_balances.map(balance => balance.asset);

    const query = `SELECT * FROM ${STAMP_TABLE} WHERE cpid IN (${assets.map(() => `?`).join(',')})`;
    const balances = await handleQueryWithClient(client, query, assets);

    const grouped = balances.rows.reduce((acc, cur) => {
      acc[cur.cpid] = acc[cur.cpid] || [];
      acc[cur.cpid].push(cur);
      return acc;
    }, {});

    const summarized = Object.keys(grouped).map(key => summarize_issuances(grouped[key]));

    return summarized.map(summary => {
      const xcp_balance = xcp_balances.find(balance => balance.asset === summary.cpid);
      return {
        ...summary,
        balance: xcp_balance ? xcp_balance.quantity : 0,
      };
    });
  } catch (error) {
    console.error("Error getting balances: ", error);
    return [];
  }
};

export const get_sends_for_cpid = async (cpid: string) => {
  const query = `
    SELECT s.*, b.block_time FROM ${SEND_TABLE} AS s
    LEFT JOIN ${BLOCK_TABLE} AS b ON s.block_index = b.block_index
    WHERE s.cpid = ?
    ORDER BY s.tx_index;
  `;
  return await handleQuery(query, [cpid]);
}

export const get_sends_for_cpid_with_client = async (client: Client, cpid: string) => {
  const query = `
    SELECT s.*, b.block_time FROM ${SEND_TABLE} AS s
    LEFT JOIN ${BLOCK_TABLE} AS b ON s.block_index = b.block_index
    WHERE s.cpid = ?
    ORDER BY s.tx_index;
  `;
  return await handleQueryWithClient(client, query, [cpid]);
}
