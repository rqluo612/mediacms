import React, { useState } from 'react';
import { ApiUrlConsumer } from '../utils/contexts/';
import { MediaListWrapper } from '../components/MediaListWrapper';
import { LazyLoadItemListAsync } from '../components/item-list/LazyLoadItemListAsync.jsx';
import { Page } from './Page';
import { translateString } from '../utils/helpers/';

import './DiscoveryPages.scss';

interface TagsPageProps {
  id?: string;
  title?: string;
}

export const TagsPage: React.FC<TagsPageProps> = ({ id = 'tags', title = translateString('Tags') }) => {
  const [itemsCount, setItemsCount] = useState<number | null>(null);

  return (
    <Page id={id}>
      <section className="discovery-page-intro">
        <span className="discovery-page-kicker">{translateString('EXPLORE')}</span>
        <h1>{title}</h1>
        <p>{translateString('Browse popular topics and jump directly to matching media.')}</p>
      </section>
      <ApiUrlConsumer>
        {(apiUrl) => (
          <MediaListWrapper className="items-list-ver discovery-taxonomy-list">
            <LazyLoadItemListAsync
              singleLinkContent={true}
              inTagsList={true}
              requestUrl={apiUrl.archive.tags}
              itemsCountCallback={setItemsCount}
            />
            {itemsCount === 0 ? (
              <div className="discovery-empty-state">
                <i className="material-icons" aria-hidden="true">local_offer</i>
                <h2>{translateString('No tags yet')}</h2>
                <p>{translateString('Tags will appear here when they are added to media.')}</p>
              </div>
            ) : null}
          </MediaListWrapper>
        )}
      </ApiUrlConsumer>
    </Page>
  );
};
