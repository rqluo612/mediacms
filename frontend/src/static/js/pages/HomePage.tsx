import React, { useState } from 'react';
import { ApiUrlConsumer, LinksConsumer } from '../utils/contexts/';
import { PageStore } from '../utils/stores/';
import { MediaListRow } from '../components/MediaListRow';
import { MediaMultiListWrapper } from '../components/MediaMultiListWrapper';
import { ItemListAsync } from '../components/item-list/ItemListAsync.jsx';
import { InlineSliderItemListAsync } from '../components/item-list/InlineSliderItemListAsync.jsx';
import { Page } from './Page';
import { translateString } from '../utils/helpers/';
import { useUser } from '../utils/hooks/';

import './HomePage.scss';

const EmptyMedia: React.FC = () => {
  const { isAnonymous } = useUser();

  return (
    <LinksConsumer>
      {(links) => (
        <div className="empty-media">
          <i className="material-icons empty-media-icon" aria-hidden="true">
            video_library
          </i>
          <div className="welcome-title">{translateString('No public media yet')}</div>
          <div className="start-uploading">
            {isAnonymous
              ? translateString('Sign in to upload the first video.')
              : translateString('Upload the first video and start sharing.')}
          </div>
          <a
            href={isAnonymous ? links.signin : links.user.addMedia}
            title={isAnonymous ? translateString('Sign in') : translateString('Upload media')}
            className="button-link"
          >
            <i className="material-icons" aria-hidden="true">
              {isAnonymous ? 'login' : 'video_call'}
            </i>
            {isAnonymous ? translateString('SIGN IN') : translateString('UPLOAD MEDIA')}
          </a>
        </div>
      )}
    </LinksConsumer>
  );
};

const HomeHero: React.FC = () => {
  const { isAnonymous } = useUser();

  return (
    <LinksConsumer>
      {(links) => (
        <section className="home-hero" aria-labelledby="home-hero-title">
          <div className="home-hero-content">
            <span className="home-hero-kicker">{translateString('VIDEO COMMUNITY')}</span>
            <h1 id="home-hero-title">{translateString('Discover, watch and share great media')}</h1>
            <p>
              {translateString(
                'Explore the latest videos, find useful content and join the conversation from any device.'
              )}
            </p>

            <form className="home-hero-search" method="get" action={links.search.base} role="search">
              <label className="sr-only" htmlFor="home-media-search">
                {translateString('Search media')}
              </label>
              <i className="material-icons" aria-hidden="true">
                search
              </i>
              <input
                id="home-media-search"
                type="search"
                name="q"
                placeholder={translateString('Search videos, categories or tags')}
                autoComplete="off"
              />
              <button type="submit">{translateString('Search')}</button>
            </form>

            <div className="home-hero-actions">
              <a className="home-primary-action" href={links.latest}>
                <i className="material-icons" aria-hidden="true">
                  play_circle
                </i>
                {translateString('Start watching')}
              </a>
              <a className="home-secondary-action" href={isAnonymous ? links.register : links.user.addMedia}>
                <i className="material-icons" aria-hidden="true">
                  {isAnonymous ? 'person_add' : 'upload'}
                </i>
                {isAnonymous ? translateString('Create account') : translateString('Upload media')}
              </a>
            </div>
          </div>

          <div className="home-hero-visual" aria-hidden="true">
            <div className="home-hero-play">
              <i className="material-icons">play_arrow</i>
            </div>
            <span className="home-orbit home-orbit-one"></span>
            <span className="home-orbit home-orbit-two"></span>
            <span className="home-orbit home-orbit-three"></span>
          </div>
        </section>
      )}
    </LinksConsumer>
  );
};

interface HomePageProps {
  id?: string;
  latest_title: string;
  featured_title: string;
  recommended_title: string;
  popular_title: string;
  latest_view_all_link: boolean;
  featured_view_all_link: boolean;
  recommended_view_all_link: boolean;
}

export const HomePage: React.FC<HomePageProps> = ({
  id = 'home',
  //featured_title = PageStore.get('config-options').pages.home.sections.featured.title,
  //recommended_title = PageStore.get('config-options').pages.home.sections.recommended.title,
  //latest_title = PageStore.get('config-options').pages.home.sections.latest.title,
  featured_title = translateString('Featured'),
  recommended_title = translateString('Recommended'),
  latest_title = translateString('Latest'),
  popular_title = translateString('Popular'),
  latest_view_all_link = false,
  featured_view_all_link = true,
  recommended_view_all_link = true,
}) => {
  const [zeroMedia, setZeroMedia] = useState(false);
  const [visibleLatest, setVisibleLatest] = useState(false);
  const [visibleFeatured, setVisibleFeatured] = useState(false);
  const [visibleRecommended, setVisibleRecommended] = useState(false);
  const [visiblePopular, setVisiblePopular] = useState(false);

  const onLoadLatest = (length: number) => {
    setVisibleLatest(0 < length);
    setZeroMedia(0 === length);
  };

  const onLoadFeatured = (length: number) => {
    setVisibleFeatured(0 < length);
  };

  const onLoadRecommended = (length: number) => {
    setVisibleRecommended(0 < length);
  };

  const onLoadPopular = (length: number) => {
    setVisiblePopular(0 < length);
  };

  return (
    <Page id={id}>
      <HomeHero />
      <LinksConsumer>
        {(links) => (
          <ApiUrlConsumer>
            {(apiUrl) => (
              <MediaMultiListWrapper className="items-list-ver home-media-sections">
                {PageStore.get('config-enabled').pages.featured &&
                  PageStore.get('config-enabled').pages.featured.enabled && (
                    <MediaListRow
                      title={featured_title}
                      style={!visibleFeatured ? { display: 'none' } : undefined}
                      viewAllLink={featured_view_all_link ? links.featured : null}
                    >
                      <InlineSliderItemListAsync
                        requestUrl={apiUrl.featured}
                        itemsCountCallback={onLoadFeatured}
                        hideViews={!PageStore.get('config-media-item').displayViews}
                        hideAuthor={!PageStore.get('config-media-item').displayAuthor}
                        hideDate={!PageStore.get('config-media-item').displayPublishDate}
                      />
                    </MediaListRow>
                  )}

                {PageStore.get('config-enabled').pages.recommended &&
                  PageStore.get('config-enabled').pages.recommended.enabled && (
                    <MediaListRow
                      title={recommended_title}
                      style={!visibleRecommended ? { display: 'none' } : undefined}
                      viewAllLink={recommended_view_all_link ? links.recommended : null}
                    >
                      <InlineSliderItemListAsync
                        requestUrl={apiUrl.recommended}
                        itemsCountCallback={onLoadRecommended}
                        hideViews={!PageStore.get('config-media-item').displayViews}
                        hideAuthor={!PageStore.get('config-media-item').displayAuthor}
                        hideDate={!PageStore.get('config-media-item').displayPublishDate}
                      />
                    </MediaListRow>
                  )}

                <MediaListRow
                  title={popular_title}
                  style={!visiblePopular ? { display: 'none' } : undefined}
                  viewAllLink={links.recommended}
                >
                  <InlineSliderItemListAsync
                    requestUrl={apiUrl.popular}
                    itemsCountCallback={onLoadPopular}
                    hideViews={!PageStore.get('config-media-item').displayViews}
                    hideAuthor={!PageStore.get('config-media-item').displayAuthor}
                    hideDate={!PageStore.get('config-media-item').displayPublishDate}
                  />
                </MediaListRow>

                <MediaListRow
                  title={latest_title}
                  style={!visibleLatest ? { display: 'none' } : undefined}
                  viewAllLink={latest_view_all_link ? links.latest : null}
                >
                  <ItemListAsync
                    pageItems={30}
                    requestUrl={apiUrl.media}
                    itemsCountCallback={onLoadLatest}
                    hideViews={!PageStore.get('config-media-item').displayViews}
                    hideAuthor={!PageStore.get('config-media-item').displayAuthor}
                    hideDate={!PageStore.get('config-media-item').displayPublishDate}
                  />
                </MediaListRow>

                {zeroMedia && <EmptyMedia />}
              </MediaMultiListWrapper>
            )}
          </ApiUrlConsumer>
        )}
      </LinksConsumer>
    </Page>
  );
};
