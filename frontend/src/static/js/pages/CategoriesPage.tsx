import React, { useState } from 'react';
import { ApiUrlConsumer } from '../utils/contexts/';
import { MediaListWrapper } from '../components/MediaListWrapper';
import { LazyLoadItemListAsync } from '../components/item-list/LazyLoadItemListAsync.jsx';
import { Page } from './Page';
import { translateString, inEmbeddedApp } from '../utils/helpers/';

import './DiscoveryPages.scss';

interface CategoriesPageProps {
  id?: string;
  title?: string;
}

export const CategoriesPage: React.FC<CategoriesPageProps> = ({
  id = 'categories',
  title = inEmbeddedApp() ? translateString('Courses') : translateString('Categories'),
}) => {
  const [itemsCount, setItemsCount] = useState<number | null>(null);

  return (
    <Page id={id}>
      <section className="discovery-page-intro">
        <span className="discovery-page-kicker">{translateString('BROWSE')}</span>
        <h1>{title}</h1>
        <p>{translateString('Explore the media library by topic and find content that interests you.')}</p>
      </section>
      <ApiUrlConsumer>
        {(apiUrl) => (
          <MediaListWrapper className="items-list-ver discovery-taxonomy-list">
            <LazyLoadItemListAsync
              singleLinkContent={true}
              inCategoriesList={true}
              requestUrl={apiUrl.archive.categories}
              itemsCountCallback={setItemsCount}
            />
            {itemsCount === 0 ? (
              <div className="discovery-empty-state">
                <i className="material-icons" aria-hidden="true">category</i>
                <h2>{translateString('No categories yet')}</h2>
                <p>{translateString('Categories will appear here after media has been organized.')}</p>
              </div>
            ) : null}
          </MediaListWrapper>
        )}
      </ApiUrlConsumer>
    </Page>
  );
};
