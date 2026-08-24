import React, { useState, useEffect } from 'react';
import { MemberContext, TextsContext } from '../../utils/contexts/';
import { MediaPageStore } from '../../utils/stores/';
import { formatViewsNumber, redirectToSignIn, translateString } from '../../utils/helpers/';
import { PageActions, MediaPageActions } from '../../utils/actions/';
import { CircleIconButton, MaterialIcon } from '../_shared/';

export function MediaDislikeIcon() {
  const [dislikedMedia, setDislikedMedia] = useState(MediaPageStore.get('user-disliked-media'));
  const [dislikesCounter, setDislikesCounter] = useState(formatViewsNumber(MediaPageStore.get('media-dislikes'), false));
  const [submitting, setSubmitting] = useState(false);

  function updateStateValues() {
    setDislikedMedia(MediaPageStore.get('user-disliked-media'));
    setDislikesCounter(formatViewsNumber(MediaPageStore.get('media-dislikes'), false));
  }

  function onCompleteMediaDislike() {
    setSubmitting(false);
    updateStateValues();
    PageActions.addNotification(TextsContext._currentValue.messages.addToDisliked, 'mediaDislike');
  }

  function onCompleteMediaDislikeCancel() {
    setSubmitting(false);
    updateStateValues();
    PageActions.addNotification(TextsContext._currentValue.messages.removeFromDisliked, 'cancelMediaDislike');
  }

  function onFailMediaDislikeRequest() {
    setSubmitting(false);
  }

  function toggleDislike(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    if (MemberContext._currentValue.is.anonymous) {
      redirectToSignIn();
      return;
    }

    if (dislikedMedia || submitting) {
      return;
    }

    setSubmitting(true);
    MediaPageActions.dislikeMedia();
  }

  useEffect(() => {
    MediaPageStore.on('disliked_media', onCompleteMediaDislike);
    MediaPageStore.on('undisliked_media', onCompleteMediaDislikeCancel);
    MediaPageStore.on('disliked_media_failed_request', onFailMediaDislikeRequest);
    return () => {
      MediaPageStore.removeListener('disliked_media', onCompleteMediaDislike);
      MediaPageStore.removeListener('undisliked_media', onCompleteMediaDislikeCancel);
      MediaPageStore.removeListener('disliked_media_failed_request', onFailMediaDislikeRequest);
    };
  }, []);

  return (
    <div className="like">
      <button
        onClick={toggleDislike}
        disabled={dislikedMedia || submitting}
        aria-pressed={dislikedMedia}
        aria-label={translateString(dislikedMedia ? 'Media disliked' : 'Dislike media')}
        title={translateString(dislikedMedia ? 'You already disliked this media' : 'Dislike media')}
      >
        <CircleIconButton type="span">
          <MaterialIcon type="thumb_down" />
        </CircleIconButton>
        <span className="dislikes-counter">{dislikesCounter}</span>
      </button>
    </div>
  );
}
