// DO NOT EDIT. This file is generated by Fresh.
// This file SHOULD be checked into source version control.
// This file is automatically updated during development when running `dev.ts`.

import * as $_404 from "./routes/_404.tsx";
import * as $_app from "./routes/_app.tsx";
import * as $api_v2_block_block_index_ from "./routes/api/v2/block/[block_index].ts";
import * as $api_v2_block_block_count_number_ from "./routes/api/v2/block/block_count/[...number].ts";
import * as $api_v2_block_related_block_index_ from "./routes/api/v2/block/related/[block_index].ts";
import * as $api_v2_cursed_id_ from "./routes/api/v2/cursed/[id].ts";
import * as $api_v2_cursed_block_block_index_ from "./routes/api/v2/cursed/block/[block_index].ts";
import * as $api_v2_cursed_ident_ident_ from "./routes/api/v2/cursed/ident/[ident].ts";
import * as $api_v2_cursed_index from "./routes/api/v2/cursed/index.ts";
import * as $api_v2_issuances_id_ from "./routes/api/v2/issuances/[id].ts";
import * as $api_v2_stamps_id_ from "./routes/api/v2/stamps/[id].ts";
import * as $api_v2_stamps_block_block_index_ from "./routes/api/v2/stamps/block/[block_index].ts";
import * as $api_v2_stamps_ident_ident_ from "./routes/api/v2/stamps/ident/[ident].ts";
import * as $api_v2_stamps_index from "./routes/api/v2/stamps/index.ts";
import * as $block_id_ from "./routes/block/[id].tsx";
import * as $content_imgpath_ from "./routes/content/[...imgpath].tsx";
import * as $cursed_index from "./routes/cursed/index.tsx";
import * as $index from "./routes/index.tsx";
import * as $stamp_id_ from "./routes/stamp/[id].tsx";
import * as $stamp_index from "./routes/stamp/index.tsx";
import * as $BlockSelector from "./islands/BlockSelector.tsx";
import * as $StampKind from "./islands/StampKind.tsx";
import { type Manifest } from "$fresh/server.ts";

const manifest = {
  routes: {
    "./routes/_404.tsx": $_404,
    "./routes/_app.tsx": $_app,
    "./routes/api/v2/block/[block_index].ts": $api_v2_block_block_index_,
    "./routes/api/v2/block/block_count/[...number].ts":
      $api_v2_block_block_count_number_,
    "./routes/api/v2/block/related/[block_index].ts":
      $api_v2_block_related_block_index_,
    "./routes/api/v2/cursed/[id].ts": $api_v2_cursed_id_,
    "./routes/api/v2/cursed/block/[block_index].ts":
      $api_v2_cursed_block_block_index_,
    "./routes/api/v2/cursed/ident/[ident].ts": $api_v2_cursed_ident_ident_,
    "./routes/api/v2/cursed/index.ts": $api_v2_cursed_index,
    "./routes/api/v2/issuances/[id].ts": $api_v2_issuances_id_,
    "./routes/api/v2/stamps/[id].ts": $api_v2_stamps_id_,
    "./routes/api/v2/stamps/block/[block_index].ts":
      $api_v2_stamps_block_block_index_,
    "./routes/api/v2/stamps/ident/[ident].ts": $api_v2_stamps_ident_ident_,
    "./routes/api/v2/stamps/index.ts": $api_v2_stamps_index,
    "./routes/block/[id].tsx": $block_id_,
    "./routes/content/[...imgpath].tsx": $content_imgpath_,
    "./routes/cursed/index.tsx": $cursed_index,
    "./routes/index.tsx": $index,
    "./routes/stamp/[id].tsx": $stamp_id_,
    "./routes/stamp/index.tsx": $stamp_index,
  },
  islands: {
    "./islands/BlockSelector.tsx": $BlockSelector,
    "./islands/StampKind.tsx": $StampKind,
  },
  baseUrl: import.meta.url,
} satisfies Manifest;

export default manifest;
