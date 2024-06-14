# btc_stamps_priv_tools

Pull changes from the private repository:

To update the subtree with the latest changes from the private repository, use:
```
git subtree pull --prefix=indexer/tools_priv https://github.com/stampchain-io/btc_stamps_priv_tools main
```

Push changes to the private repository:

If you make changes in the subtree directory and want to push them to the private repository, use:

```
git subtree push --prefix=indexer/tools_priv https://github.com/stampchain-io/btc_stamps_priv_tools main
```