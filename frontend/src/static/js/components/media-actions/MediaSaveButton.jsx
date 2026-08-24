import React, { useState } from 'react';
import { usePopup } from '../../utils/hooks/';
import { CircleIconButton, MaterialIcon, NavigationContentApp, PopupMain } from '../_shared/';
import { PlaylistsSelection } from '../playlists-selection/PlaylistsSelection';
import { MemberContext } from '../../utils/contexts/';
import { redirectToSignIn, translateString } from '../../utils/helpers/';

function mediaSavePopupPages(onTriggerPopupClose) {
  return {
    selectPlaylist: (
      <div className="popup-fullscreen">
        <PopupMain>
          <span className="popup-fullscreen-overlay"></span>
          <PlaylistsSelection triggerPopupClose={onTriggerPopupClose} />
        </PopupMain>
      </div>
    ),
    createPlaylist: (
      <div className="popup-fullscreen">
        <PopupMain>
          <span className="popup-fullscreen-overlay"></span>
        </PopupMain>
      </div>
    ),
  };
}

export function MediaSaveButton(props) {
  const [popupContentRef, PopupContent, PopupTrigger] = usePopup();

  const [popupCurrentPage, setPopupCurrentPage] = useState('selectPlaylist');

  function triggerPopupClose() {
    popupContentRef.current.toggle();
  }

  function requireLogin(event) {
    if (!MemberContext._currentValue.is.anonymous) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    redirectToSignIn();
  }

  return (
    <div className="save">
      <PopupTrigger contentRef={popupContentRef}>
        <button
          onClick={requireLogin}
          aria-label={translateString('Save media to playlist')}
          title={translateString(
            MemberContext._currentValue.is.anonymous
              ? 'Sign in to save media'
              : 'Save media to playlist'
          )}
        >
          <CircleIconButton type="span">
            <MaterialIcon type="playlist_add" />
          </CircleIconButton>
          <span>{translateString("SAVE")}</span>
        </button>
      </PopupTrigger>

      <PopupContent contentRef={popupContentRef}>
        <NavigationContentApp
          initPage={popupCurrentPage}
          pageChangeSelector={'.change-page'}
          pageIdSelectorAttr={'data-page-id'}
          pages={mediaSavePopupPages(triggerPopupClose)}
          focusFirstItemOnPageChange={false}
          pageChangeCallback={setPopupCurrentPage}
        />
      </PopupContent>
    </div>
  );
}
