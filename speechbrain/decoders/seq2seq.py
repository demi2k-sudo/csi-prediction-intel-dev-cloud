"""Decoding methods for seq2seq autoregressive model.

Authors
 * Adel Moumen 2022, 2023
 * Ju-Chieh Chou 2020
 * Peter Plantinga 2020
 * Mirco Ravanelli 2020
 * Sung-Lin Yeh 2020
"""
import torch
from speechbrain.decoders.utils import (
    inflate_tensor,
    mask_by_condition,
    _update_mem,
)
from speechbrain.utils.data_utils import undo_padding


class AlivedHypotheses(torch.nn.Module):
    """ This class handle the data for the hypotheses during the decoding.

    Arguments
    ---------
    alived_seq : torch.Tensor
        The sequence of tokens for each hypothesis.
    alived_log_probs : torch.Tensor
        The log probabilities of each token for each hypothesis.
    sequence_scores : torch.Tensor
        The sum of log probabilities for each hypothesis.
    """

    def __init__(
        self, alived_seq, alived_log_probs, sequence_scores,
    ):
        super().__init__()
        self.alived_seq = alived_seq
        self.alived_log_probs = alived_log_probs
        self.sequence_scores = sequence_scores


class S2SBaseSearcher(torch.nn.Module):
    """S2SBaseSearcher class to be inherited by other
    decoding approaches for seq2seq model.

    Arguments
    ---------
    bos_index : int
        The index of the beginning-of-sequence (bos) token.
    eos_index : int
        The index of end-of-sequence (eos) token.
    min_decode_radio : float
        The ratio of minimum decoding steps to the length of encoder states.
    max_decode_radio : float
        The ratio of maximum decoding steps to the length of encoder states.

    Returns
    -------
    hyps
        The predicted tokens, as a list of lists or, if return_topk is True,
        a Tensor of shape (batch, topk, max length of token_id sequences).
    top_lengths
        The length of each topk sequence in the batch.
    top_scores
        This final scores of topk hypotheses.
    top_log_probs
        The log probabilities of each hypotheses.
    """

    def __init__(
        self, bos_index, eos_index, min_decode_ratio, max_decode_ratio,
    ):
        super(S2SBaseSearcher, self).__init__()
        self.bos_index = bos_index
        self.eos_index = eos_index
        self.min_decode_ratio = min_decode_ratio
        self.max_decode_ratio = max_decode_ratio

    def forward(self, enc_states, wav_len):
        """This method should implement the forward algorithm of decoding method.

        Arguments
        ---------
        enc_states : torch.Tensor
            The precomputed encoder states to be used when decoding.
            (ex. the encoded speech representation to be attended).
        wav_len : torch.Tensor
            The speechbrain-style relative length.
        """
        raise NotImplementedError

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """This method should implement one step of
        forwarding operation in the autoregressive model.

        Arguments
        ---------
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        enc_states : torch.Tensor
            The encoder states to be attended.
        enc_lens : torch.Tensor
            The actual length of each enc_states sequence.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        memory : No limit
            The memory variables generated in this step.
            (ex. RNN hidden states).
        attn : torch.Tensor
            The attention weight for doing penalty.
        """
        raise NotImplementedError

    def reset_mem(self, batch_size, device):
        """This method should implement the resetting of
        memory variables for the seq2seq model.
        E.g., initializing zero vector as initial hidden states.

        Arguments
        ---------
        batch_size : int
            The size of the batch.
        device : torch.device
            The device to put the initial variables.

        Return
        ------
        memory : No limit
            The initial memory variable.
        """
        raise NotImplementedError

    def change_max_decoding_length(self, min_decode_steps, max_decode_steps):
        """set the minimum/maximum length the decoder can take."""
        return min_decode_steps, max_decode_steps

    def set_n_out(self):
        """set the number of output tokens.
        Overrides this function if the fc layer is embedded
        in the model, e.g., Whisper.
        """
        return self.fc.w.out_features


class S2SGreedySearcher(S2SBaseSearcher):
    """This class implements the general forward-pass of
    greedy decoding approach. See also S2SBaseSearcher().
    """

    def forward(self, enc_states, wav_len):
        """This method performs a greedy search.

        Arguments
        ---------
        enc_states : torch.Tensor
            The precomputed encoder states to be used when decoding.
            (ex. the encoded speech representation to be attended).
        wav_len : torch.Tensor
            The speechbrain-style relative length.

        Returns
        -------
        hyps : List containing hypotheses.
        top_lengths : torch.Tensor (batch)
            This tensor contains the final scores of hypotheses.
        top_scores : torch.Tensor (batch)
            The length of each topk sequence in the batch.
        top_log_probs : torch.Tensor (batch, max length of token_id sequences)
            The log probabilities of each hypotheses.
        """
        enc_lens = torch.round(enc_states.shape[1] * wav_len).int()
        device = enc_states.device
        batch_size = enc_states.shape[0]

        memory = self.reset_mem(batch_size, device=device)

        # Using bos as the first input
        inp_tokens = (
            enc_states.new_zeros(batch_size).fill_(self.bos_index).long()
        )

        log_probs_lst = []
        max_decode_steps = int(enc_states.shape[1] * self.max_decode_ratio)

        # the decoding steps can be based on the max number of tokens that a decoder can process
        # (e.g., 448 for Whisper).
        _, max_decode_steps = self.change_max_decoding_length(
            0, max_decode_steps
        )

        has_ended = enc_states.new_zeros(batch_size).bool()
        for _ in range(max_decode_steps):
            log_probs, memory, _ = self.forward_step(
                inp_tokens, memory, enc_states, enc_lens
            )
            log_probs_lst.append(log_probs)
            inp_tokens = log_probs.argmax(dim=-1)
            log_probs[has_ended] = float("inf")
            has_ended = has_ended | (inp_tokens == self.eos_index)
            if has_ended.all():
                break

        log_probs = torch.stack(log_probs_lst, dim=1)
        scores, predictions = log_probs.max(dim=-1)
        mask = scores == float("inf")
        scores[mask] = 0
        predictions[mask] = self.eos_index

        (
            top_hyps,
            top_lengths,
            top_scores,
            top_log_probs,
        ) = self._get_top_prediction(predictions, scores, log_probs)

        # Convert best hypothesis to list
        hyps = undo_padding(top_hyps[:, 0], top_lengths)

        return hyps, top_lengths, top_scores, top_log_probs

    def _get_top_prediction(self, hyps, scores, log_probs):
        """This method sorts the scores and return corresponding hypothesis and log probs.

        Arguments
        ---------
        hyps : torch.Tensor (batch, max length of token_id sequences)
            This tensor stores the predicted hypothesis.
        scores : torch.Tensor (batch)
            The score of each hypotheses.
        log_probs : torch.Tensor (batch, max length of token_id sequences)
            The log probabilities of each hypotheses.

        Returns
        -------
        top_hyps : torch.Tensor (batch, max length of token_id sequences)
            This tensor stores the topk predicted hypothesis.
        top_lengths : torch.Tensor (batch)
            This tensor contains the final scores of hypotheses.
        top_scores : torch.Tensor (batch)
            The length of each topk sequence in the batch.
        top_log_probs : torch.Tensor (batch, max length of token_id sequences)
            The log probabilities of each hypotheses.
        """
        batch_size = hyps.size(0)
        max_length = hyps.size(1)
        top_lengths = [max_length] * batch_size

        # Collect lengths of top hyps
        for pred_index in range(batch_size):
            pred = hyps[pred_index]
            pred_length = (pred == self.eos_index).nonzero(as_tuple=False)
            if len(pred_length) > 0:
                top_lengths[pred_index] = pred_length[0].item()
        # Convert lists to tensors
        top_lengths = torch.tensor(
            top_lengths, dtype=torch.float, device=hyps.device
        )

        # Pick top log probabilities
        top_log_probs = log_probs

        # Use SpeechBrain style lengths
        top_lengths = (top_lengths - 1).abs() / max_length

        return (
            hyps.unsqueeze(1),
            top_lengths.unsqueeze(1),
            scores.unsqueeze(1),
            top_log_probs.unsqueeze(1),
        )


class S2SRNNGreedySearcher(S2SGreedySearcher):
    """
    This class implements the greedy decoding
    for AttentionalRNNDecoder (speechbrain/nnet/RNN.py).
    See also S2SBaseSearcher() and S2SGreedySearcher().

    Arguments
    ---------
    embedding : torch.nn.Module
        An embedding layer.
    decoder : torch.nn.Module
        Attentional RNN decoder.
    linear : torch.nn.Module
        A linear output layer.
    **kwargs
        see S2SBaseSearcher, arguments are directly passed.

    Example
    -------
    >>> import speechbrain as sb
    >>> from speechbrain.decoders import S2SRNNGreedySearcher
    >>> emb = torch.nn.Embedding(5, 3)
    >>> dec = sb.nnet.RNN.AttentionalRNNDecoder(
    ...     "gru", "content", 3, 3, 1, enc_dim=7, input_size=3
    ... )
    >>> lin = sb.nnet.linear.Linear(n_neurons=5, input_size=3)
    >>> searcher = S2SRNNGreedySearcher(
    ...     embedding=emb,
    ...     decoder=dec,
    ...     linear=lin,
    ...     bos_index=0,
    ...     eos_index=1,
    ...     min_decode_ratio=0,
    ...     max_decode_ratio=1,
    ... )
    >>> batch_size = 2
    >>> enc = torch.rand([batch_size, 6, 7])
    >>> wav_len = torch.ones([batch_size])
    >>> top_hyps, top_lengths, _, _ = searcher(enc, wav_len)
    """

    def __init__(self, embedding, decoder, linear, **kwargs):
        super(S2SRNNGreedySearcher, self).__init__(**kwargs)
        self.emb = embedding
        self.dec = decoder
        self.fc = linear
        self.softmax = torch.nn.LogSoftmax(dim=-1)

    def reset_mem(self, batch_size, device):
        """When doing greedy search, keep hidden state (hs) and context vector (c)
        as memory.
        """
        hs = None
        self.dec.attn.reset()
        c = torch.zeros(batch_size, self.dec.attn_dim, device=device)
        return hs, c

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        hs, c = memory
        e = self.emb(inp_tokens)
        dec_out, hs, c, w = self.dec.forward_step(
            e, hs, c, enc_states, enc_lens
        )
        log_probs = self.softmax(self.fc(dec_out))
        return log_probs, (hs, c), w


class S2SBeamSearcher(S2SBaseSearcher):
    """This class implements the beam-search algorithm for the seq2seq model.
    See also S2SBaseSearcher().

    Arguments
    ---------
    bos_index : int
        The index of beginning-of-sequence token.
    eos_index : int
        The index of end-of-sequence token.
    min_decode_radio : float
        The ratio of minimum decoding steps to length of encoder states.
    max_decode_radio : float
        The ratio of maximum decoding steps to length of encoder states.
    beam_size : int
        The width of beam.
    scorer: speechbrain.decoders.scorers.ScorerBuilder
        Scorer instance. Default: None.
    return_topk : bool
        Whether to return topk hypotheses. The topk hypotheses will be
        padded to the same length. Default: False.
    topk : int
        If return_topk is True, then return topk hypotheses. Default: 1.
    using_eos_threshold : bool
        Whether to use eos threshold. Default: True.
    eos_threshold : float
        The threshold coefficient for eos token. Default: 1.5.
        See 3.1.2 in reference: https://arxiv.org/abs/1904.02619
    length_normalization : bool
        Whether to divide the scores by the length. Default: True.
    using_max_attn_shift: bool
        Whether using the max_attn_shift constraint. Default: False.
    max_attn_shift: int
        Beam search will block the beams that attention shift more
        than max_attn_shift. Default: 60.
        Reference: https://arxiv.org/abs/1904.02619
    minus_inf : float
        The value of minus infinity to block some path
        of the search. Default: -1e20.
    """

    def __init__(
        self,
        bos_index,
        eos_index,
        min_decode_ratio,
        max_decode_ratio,
        beam_size,
        scorer=None,
        return_topk=False,
        topk=1,
        using_eos_threshold=True,
        eos_threshold=1.5,
        length_normalization=True,
        using_max_attn_shift=False,
        max_attn_shift=60,
        minus_inf=-1e20,
    ):
        super(S2SBeamSearcher, self).__init__(
            bos_index, eos_index, min_decode_ratio, max_decode_ratio,
        )
        self.beam_size = beam_size
        self.scorer = scorer
        self.return_topk = return_topk
        self.topk = topk
        self.length_normalization = length_normalization
        self.using_eos_threshold = using_eos_threshold
        self.eos_threshold = eos_threshold
        self.using_max_attn_shift = using_max_attn_shift
        self.max_attn_shift = max_attn_shift
        self.attn_weight = 1.0
        self.ctc_weight = 0.0
        self.minus_inf = minus_inf

        if self.scorer is not None:
            # Check length normalization
            if length_normalization and self.scorer.weights["length"] > 0.0:
                raise ValueError(
                    "Length normalization is not compatible with length rewarding."
                )
            if self.scorer.weights["ctc"] > 0.0:
                # Check indices for ctc
                all_scorers = {
                    **self.scorer.full_scorers,
                    **self.scorer.partial_scorers,
                }
                blank_index = all_scorers["ctc"].blank_index
                if len({bos_index, eos_index, blank_index}) < 3:
                    raise ValueError(
                        "Set blank, eos and bos to different indexes for joint ATT/CTC or CTC decoding"
                    )

                self.ctc_weight = self.scorer.weights["ctc"]
                self.attn_weight = 1.0 - self.ctc_weight

    def _check_full_beams(self, hyps):
        """This method checks whether hyps has been full.

        Arguments
        ---------
        hyps : List
            This list contains batch_size number.
            Each inside list contains a list stores all the hypothesis for this sentence.

        Returns
        -------
        bool
            Whether the hyps has been full.
        """
        hyps_len = [len(lst) for lst in hyps]
        beams_size = [self.beam_size for _ in range(len(hyps_len))]
        return hyps_len == beams_size

    def _check_attn_shift(self, attn, prev_attn_peak):
        """This method checks whether attention shift is more than attn_shift.

        Arguments
        ---------
        attn : torch.Tensor
            The attention to be checked.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.

        Returns
        -------
        cond : torch.BoolTensor
            Each element represents whether the beam is within the max_shift range.
        attn_peak : torch.Tensor
            The peak of the attn tensor.
        """
        # Block the candidates that exceed the max shift
        _, attn_peak = torch.max(attn, dim=1)
        lt_cond = attn_peak <= (prev_attn_peak + self.max_attn_shift)
        mt_cond = attn_peak > (prev_attn_peak - self.max_attn_shift)

        # True if not exceed limit
        # Multiplication equals to element-wise and for tensor
        cond = (lt_cond * mt_cond).unsqueeze(1)
        return cond, attn_peak

    def _check_eos_threshold(self, log_probs):
        """This method checks whether eos log-probabilities exceed threshold.

        Arguments
        ---------
        log_probs : torch.Tensor
            The log-probabilities.

        Returns
        ------
        cond : torch.BoolTensor
            Each element represents whether the eos log-probabilities will be kept.
        """
        max_probs, _ = torch.max(log_probs, dim=-1)
        eos_probs = log_probs[:, self.eos_index]
        cond = eos_probs > (self.eos_threshold * max_probs)
        return cond

    def init_hypotheses(self):
        """This method initializes the AlivedHypotheses object.

        Returns
        -------
        AlivedHypotheses
            The alived hypotheses filled with the initial values.
        """
        return AlivedHypotheses(
            alived_seq=torch.empty(self.n_bh, 0, device=self.device).long(),
            alived_log_probs=torch.empty(self.n_bh, 0, device=self.device),
            sequence_scores=torch.empty(self.n_bh, device=self.device)
            .fill_(float("-inf"))
            .index_fill_(0, self.beam_offset, 0.0),
        )

    def _attn_weight_step(
        self, inp_tokens, memory, enc_states, enc_lens, attn, log_probs
    ):
        """This method computes a forward_step if attn_weight is superior to 0.

        Arguments
        ---------
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        enc_states : torch.Tensor
            The encoder states to be attended.
        enc_lens : torch.Tensor
            The actual length of each enc_states sequence.
        attn : torch.Tensor
            The attention weight.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        memory : No limit
            The memory variables generated in this step.
            (ex. RNN hidden states).
        attn : torch.Tensor
            The attention weight.
        """
        if self.attn_weight > 0:
            log_probs, memory, attn = self.forward_step(
                inp_tokens, memory, enc_states, enc_lens
            )
            log_probs = self.attn_weight * log_probs
        return log_probs, memory, attn

    def _max_attn_shift_step(self, attn, prev_attn_peak, log_probs):
        """This method will block the beams that attention shift more
        than max_attn_shift.

        Arguments
        ---------
        attn : torch.Tensor
            The attention weight.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        """
        if self.using_max_attn_shift:
            cond, prev_attn_peak = self._check_attn_shift(attn, prev_attn_peak)
            log_probs = mask_by_condition(
                log_probs, cond, fill_value=self.minus_inf
            )
        return log_probs, prev_attn_peak

    def _scorer_step(self, inp_tokens, scorer_memory, attn, log_probs):
        """This method call the scorers if scorer is not None.

        Arguments
        ---------
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        scorer_memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        attn : torch.Tensor
            The attention weight.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        scorer_memory : No limit
            The memory variables generated in this step.
        """
        if self.scorer is not None:
            log_probs, scorer_memory = self.scorer.score(
                inp_tokens, scorer_memory, attn, log_probs, self.beam_size,
            )
        return log_probs, scorer_memory

    def _set_eos_minus_inf_step(self, log_probs, step, min_decode_steps):
        """This method set the log_probs of eos to minus infinity if the step is less than min_decode_steps.

        Arguments
        ---------
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        step : int
            The current decoding step.
        min_decode_steps : int
            The minimum decoding steps.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        """
        if step < min_decode_steps:
            log_probs[:, self.eos_index] = self.minus_inf
        return log_probs

    def _eos_threshold_step(self, log_probs):
        """This method set the log_probs of eos to minus infinity if the eos log-probabilities is less than eos_threshold.

        Arguments
        ---------
        log_probs : torch.Tensor
            The log-probabilities of the current step output.

        Returns
        -------
        log_probs : torch.Tensor
            Log-probabilities of the current step output.
        """
        if self.using_eos_threshold:
            cond = self._check_eos_threshold(log_probs)
            log_probs[:, self.eos_index] = mask_by_condition(
                log_probs[:, self.eos_index], cond, fill_value=self.minus_inf,
            )
        return log_probs

    def _attn_weight_permute_memory_step(self, memory, predecessors):
        """This method permute the memory if attn_weight is superior to 0.

        Arguments
        ---------
        memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.

        Returns
        -------
        memory : No limit
            The memory variables generated in this step.
            (ex. RNN hidden states).
        """
        if self.attn_weight > 0:
            memory = self.permute_mem(memory, index=predecessors)
        return memory

    def _scorer_permute_memory_step(
        self, scorer_memory, predecessors, candidates
    ):
        """This method permute the scorer_memory if scorer is not None.

        Arguments
        ---------
        scorer_memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.
        candidates : torch.Tensor
            The index of the current top-K output.

        Returns
        -------
        scorer_memory : No limit
            The memory variables generated in this step.
        """
        if self.scorer is not None:
            scorer_memory = self.scorer.permute_scorer_mem(
                scorer_memory, index=predecessors, candidates=candidates
            )
        return scorer_memory

    def _max_attn_shift_permute_memory_step(self, prev_attn_peak, predecessors):
        """This method permute the prev_attn_peak if using_max_attn_shift is True.

        Arguments
        ---------
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.

        Returns
        -------
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        """
        if self.using_max_attn_shift:
            prev_attn_peak = torch.index_select(
                prev_attn_peak, dim=0, index=predecessors
            )
        return prev_attn_peak

    def _update_reset_memory(self, enc_states, enc_lens):
        """ Call reset memory for each module.

        Arguments
        ---------
        enc_states : torch.Tensor
            The encoder states to be attended.
        enc_lens : torch.Tensor
            The actual length of each enc_states sequence.

        Returns
        -------
        memory : No limit
            The memory variables generated in this step.
        scorer_memory : No limit
            The memory variables generated in this step.
        """
        memory = self.reset_mem(self.n_bh, device=self.device)
        scorer_memory = None
        if self.scorer is not None:
            scorer_memory = self.scorer.reset_scorer_mem(enc_states, enc_lens)
        return memory, scorer_memory

    def _update_permute_memory(
        self, memory, scorer_memory, predecessors, candidates, prev_attn_peak
    ):
        """Call permute memory for each module. It allows us to synchronize the memory with the output.

        Arguments
        ---------
        memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        scorer_memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.
        candidates : torch.Tensor
            The index of the current top-K output.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.

        Returns
        -------
        memory : No limit
            The memory variables generated in this step.
        scorer_memory : No limit
            The memory variables generated in this step.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        """
        memory = self._attn_weight_permute_memory_step(memory, predecessors)

        scorer_memory = self._scorer_permute_memory_step(
            scorer_memory, predecessors, candidates
        )

        # If using_max_attn_shift, then the previous attn peak has to be permuted too.
        prev_attn_peak = self._max_attn_shift_permute_memory_step(
            prev_attn_peak, predecessors
        )

        return memory, scorer_memory, prev_attn_peak

    def _update_sequences_and_log_probs(
        self, log_probs, inp_tokens, predecessors, candidates, alived_hyps,
    ):
        """This method update sequences and log probabilities by adding the new inp_tokens.

        Arguments
        ---------
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.
        candidates : torch.Tensor
            The index of the current top-K output.
        alived_hyps : AlivedHypotheses
            The alived hypotheses.

        Returns
        -------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        """
        # Update alived_seq
        alived_hyps.alived_seq = torch.cat(
            [
                torch.index_select(
                    alived_hyps.alived_seq, dim=0, index=predecessors
                ),
                inp_tokens.unsqueeze(1),
            ],
            dim=-1,
        )

        # Takes the log-probabilities
        beam_log_probs = log_probs[
            torch.arange(self.batch_size).unsqueeze(1), candidates
        ].reshape(self.n_bh)

        # Update alived_log_probs
        alived_hyps.alived_log_probs = torch.cat(
            [
                torch.index_select(
                    alived_hyps.alived_log_probs, dim=0, index=predecessors
                ),
                beam_log_probs.unsqueeze(1),
            ],
            dim=-1,
        )

        return alived_hyps

    def _compute_scores_and_next_inp_tokens(self, alived_hyps, log_probs, step):
        """Compute scores and next input tokens.

        Arguments
        ---------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        step : int
            The current decoding step.

        Returns
        -------
        scores : torch.Tensor
            The scores of the current step output.
        candidates : torch.Tensor
            The index of the current top-K output.
        predecessors : torch.Tensor
            The index of which beam the current top-K output came from in (t-1) steps.
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        """
        scores = alived_hyps.sequence_scores.unsqueeze(1).expand(-1, self.n_out)
        scores = scores + log_probs

        # length normalization
        if self.length_normalization:
            scores = scores / (step + 1)

        # keep topk beams
        scores, candidates = scores.view(self.batch_size, -1).topk(
            self.beam_size, dim=-1
        )

        # The input for the next step, also the output of current step.
        inp_tokens = (candidates % self.n_out).view(self.n_bh)

        scores = scores.view(self.n_bh)
        alived_hyps.sequence_scores = scores

        # recover the length normalization
        if self.length_normalization:
            alived_hyps.sequence_scores = alived_hyps.sequence_scores * (
                step + 1
            )

        # The index of which beam the current top-K output came from in (t-1) steps.
        predecessors = (
            torch.div(candidates, self.n_out, rounding_mode="floor")
            + self.beam_offset.unsqueeze(1).expand_as(candidates)
        ).view(self.n_bh)

        return (
            scores,
            candidates,
            predecessors,
            inp_tokens,
            alived_hyps,
        )

    def init_beam_search_data(self, enc_states, wav_len):
        """Initialize the beam search data.

        Arguments
        ---------
        enc_states : torch.Tensor
            The encoder states to be attended.
        wav_len : torch.Tensor
            The actual length of each enc_states sequence.

        Returns
        -------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        memory : No limit
            The memory variables generated in this step.
        scorer_memory : No limit
            The memory variables generated in this step.
        attn : torch.Tensor
            The attention weight.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        enc_states : torch.Tensor
            The encoder states to be attended.
        enc_lens : torch.Tensor
            The actual length of each enc_states sequence.
        """
        enc_lens = torch.round(enc_states.shape[1] * wav_len).int()

        self.device = enc_states.device
        self.batch_size = enc_states.shape[0]
        self.n_bh = self.batch_size * self.beam_size

        self.n_out = self.set_n_out()

        memory, scorer_memory = self._update_reset_memory(enc_states, enc_lens)

        # Inflate the enc_states and enc_len by beam_size times
        enc_states = inflate_tensor(enc_states, times=self.beam_size, dim=0)
        enc_lens = inflate_tensor(enc_lens, times=self.beam_size, dim=0)

        # Using bos as the first input
        inp_tokens = (
            torch.zeros(self.n_bh, device=self.device)
            .fill_(self.bos_index)
            .long()
        )

        # The first index of each sentence.
        self.beam_offset = (
            torch.arange(self.batch_size, device=self.device) * self.beam_size
        )

        # initialize sequence scores variables.
        sequence_scores = torch.empty(self.n_bh, device=self.device).fill_(
            self.minus_inf
        )

        # keep only the first to make sure no redundancy.
        sequence_scores.index_fill_(0, self.beam_offset, 0.0)

        # keep the hypothesis that reaches eos and their corresponding score and log_probs.
        eos_hyps_and_log_probs_scores = [[] for _ in range(self.batch_size)]

        self.min_decode_steps = int(enc_states.shape[1] * self.min_decode_ratio)
        self.max_decode_steps = int(enc_states.shape[1] * self.max_decode_ratio)

        # the decoding steps can be based on the max number of tokens that a decoder can process
        # (e.g., 448 for Whisper).
        (
            self.min_decode_steps,
            self.max_decode_steps,
        ) = self.change_max_decoding_length(
            self.min_decode_steps, self.max_decode_steps
        )

        # Initialize the previous attention peak to zero
        # This variable will be used when using_max_attn_shift=True
        prev_attn_peak = torch.zeros(self.n_bh, device=self.device)
        attn = None

        log_probs = torch.full((self.n_bh, self.n_out), 0.0, device=self.device)

        alived_hyps = self.init_hypotheses()

        return (
            alived_hyps,
            inp_tokens,
            log_probs,
            eos_hyps_and_log_probs_scores,
            memory,
            scorer_memory,
            attn,
            prev_attn_peak,
            enc_states,
            enc_lens,
        )

    def _update_hyps_and_scores_if_eos_token(
        self, inp_tokens, alived_hyps, eos_hyps_and_log_probs_scores, scores,
    ):
        """This method will update hyps and scores if inp_tokens are eos.

        Arguments
        ---------
        inp_tokens : torch.Tensor
            The current output.
        alived_hyps : AlivedHypotheses
            alived_seq : torch.Tensor
            alived_log_probs : torch.Tensor
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        scores : torch.Tensor
            Scores at the current step.

        Returns
        -------
        is_eos : torch.BoolTensor
            Each element represents whether the token is eos.
        """
        is_eos = inp_tokens.eq(self.eos_index)
        (eos_indices,) = torch.nonzero(is_eos, as_tuple=True)

        # Store the hypothesis and their scores when reaching eos.
        if eos_indices.shape[0] > 0:
            for index in eos_indices:
                # convert to int
                index = index.item()
                batch_id = torch.div(
                    index, self.beam_size, rounding_mode="floor"
                )
                if (
                    len(eos_hyps_and_log_probs_scores[batch_id])
                    == self.beam_size
                ):
                    continue
                hyp = alived_hyps.alived_seq[index, :]
                log_probs = alived_hyps.alived_log_probs[index, :]
                final_scores = scores[index].clone()
                eos_hyps_and_log_probs_scores[batch_id].append(
                    (hyp, log_probs, final_scores)
                )

        return is_eos

    def _get_topk_prediction(self, eos_hyps_and_log_probs_scores):
        """This method sorts the scores and return corresponding hypothesis and log probs.

        Arguments
        ---------
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.

        Returns
        -------
        topk_hyps : torch.Tensor (batch, topk, max length of token_id sequences)
            This tensor stores the topk predicted hypothesis.
        topk_lengths : torch.Tensor (batch, topk)
            This tensor contains the final scores of topk hypotheses.
        topk_scores : torch.Tensor (batch, topk)
            The length of each topk sequence in the batch.
        topk_log_probs : torch.Tensor (batch, topk, max length of token_id sequences)
            The log probabilities of each hypotheses.
        """
        top_hyps, top_log_probs, top_scores, top_lengths = [], [], [], []
        batch_size = len(eos_hyps_and_log_probs_scores)

        # Collect hypotheses
        for i in range(len(eos_hyps_and_log_probs_scores)):
            hyps, log_probs, scores = zip(*eos_hyps_and_log_probs_scores[i])
            top_hyps += hyps
            top_scores += scores
            top_log_probs += log_probs
            top_lengths += [len(hyp) for hyp in hyps]

        # Convert lists to tensors
        top_hyps = torch.nn.utils.rnn.pad_sequence(
            top_hyps, batch_first=True, padding_value=0
        )
        top_log_probs = torch.nn.utils.rnn.pad_sequence(
            top_log_probs, batch_first=True, padding_value=0
        )
        top_lengths = torch.tensor(
            top_lengths, dtype=torch.float, device=top_hyps.device
        )
        top_scores = torch.stack((top_scores), dim=0).view(batch_size, -1)

        # Use SpeechBrain style lengths
        top_lengths = (top_lengths - 1).abs() / top_hyps.size(1)

        # Get topk indices
        topk_scores, indices = top_scores.topk(self.topk, dim=-1)
        indices = (indices + self.beam_offset.unsqueeze(1)).view(
            batch_size * self.topk
        )
        # Select topk hypotheses
        topk_hyps = torch.index_select(top_hyps, dim=0, index=indices,)
        topk_hyps = topk_hyps.view(batch_size, self.topk, -1)
        topk_lengths = torch.index_select(top_lengths, dim=0, index=indices,)
        topk_lengths = topk_lengths.view(batch_size, self.topk)
        topk_log_probs = torch.index_select(
            top_log_probs, dim=0, index=indices,
        )
        topk_log_probs = topk_log_probs.view(batch_size, self.topk, -1)

        return topk_hyps, topk_lengths, topk_scores, topk_log_probs

    def search_step(
        self,
        alived_hyps,
        inp_tokens,
        log_probs,
        eos_hyps_and_log_probs_scores,
        memory,
        scorer_memory,
        attn,
        prev_attn_peak,
        enc_states,
        enc_lens,
        step,
    ):
        """A search step for the next most likely tokens.

        Arguments
        ---------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        scorer_memory : No limit
            The memory variables input for this step.
            (ex. RNN hidden states).
        attn : torch.Tensor
            The attention weight.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        enc_states : torch.Tensor
            The encoder states to be attended.
        enc_lens : torch.Tensor
            The actual length of each enc_states sequence.
        step : int
            The current decoding step.

        Returns
        -------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        inp_tokens : torch.Tensor
            The input tensor of the current step.
        log_probs : torch.Tensor
            The log-probabilities of the current step output.
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        memory : No limit
            The memory variables generated in this step.
        scorer_memory : No limit
            The memory variables generated in this step.
        attn : torch.Tensor
            The attention weight.
        prev_attn_peak : torch.Tensor
            The previous attention peak place.
        scores : torch.Tensor
            The scores of the current step output.
        """
        (log_probs, memory, attn,) = self._attn_weight_step(
            inp_tokens, memory, enc_states, enc_lens, attn, log_probs,
        )

        # Keep the original value
        log_probs_clone = log_probs.clone().reshape(self.batch_size, -1)

        (log_probs, prev_attn_peak,) = self._max_attn_shift_step(
            attn, prev_attn_peak, log_probs,
        )

        log_probs = self._set_eos_minus_inf_step(
            log_probs, step, self.min_decode_steps,
        )

        log_probs = self._eos_threshold_step(log_probs)

        (log_probs, scorer_memory,) = self._scorer_step(
            inp_tokens, scorer_memory, attn, log_probs,
        )

        (
            scores,
            candidates,
            predecessors,
            inp_tokens,
            alived_hyps,
        ) = self._compute_scores_and_next_inp_tokens(
            alived_hyps, log_probs, step,
        )

        memory, scorer_memory, prev_attn_peak = self._update_permute_memory(
            memory, scorer_memory, predecessors, candidates, prev_attn_peak
        )

        alived_hyps = self._update_sequences_and_log_probs(
            log_probs_clone, inp_tokens, predecessors, candidates, alived_hyps,
        )

        is_eos = self._update_hyps_and_scores_if_eos_token(
            inp_tokens, alived_hyps, eos_hyps_and_log_probs_scores, scores,
        )

        # Block the paths that have reached eos.
        alived_hyps.sequence_scores.masked_fill_(is_eos, float("-inf"))

        return (
            alived_hyps,
            inp_tokens,
            log_probs,
            eos_hyps_and_log_probs_scores,
            memory,
            scorer_memory,
            attn,
            prev_attn_peak,
            scores,
        )

    def _fill_alived_hyps_with_eos_token(
        self, alived_hyps, eos_hyps_and_log_probs_scores, scores,
    ):
        """Fill the alived_hyps that have not reached eos with eos.

        Arguments
        ---------
        alived_hyps : AlivedHypotheses
            The alived hypotheses.
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        scores : torch.Tensor
            The scores of the current step output.

        Returns
        -------
        eos_hyps_and_log_probs_scores : list
            Generated hypotheses (the one that haved reached eos) and log probs scores.
        """
        if not self._check_full_beams(eos_hyps_and_log_probs_scores):
            # Using all eos to fill-up the hyps.
            inp_tokens = (
                torch.zeros(self.n_bh, device=self.device)
                .fill_(self.eos_index)
                .long()
            )
            self._update_hyps_and_scores_if_eos_token(
                inp_tokens, alived_hyps, eos_hyps_and_log_probs_scores, scores,
            )

        return eos_hyps_and_log_probs_scores

    def forward(self, enc_states, wav_len):  # noqa: C901
        """Applies beamsearch and returns the predicted tokens.

        Arguments
        ---------
        enc_states : torch.Tensor
            The encoder states to be attended.
        wav_len : torch.Tensor
            The actual length of each enc_states sequence.

        Returns
        -------
        hyps : list
            The predicted tokens.
        best_lens : torch.Tensor
            The length of each predicted tokens.
        best_scores : torch.Tensor
            The scores of each predicted tokens.
        best_log_probs : torch.Tensor
            The log probabilities of each predicted tokens.
        """
        (
            alived_hyps,
            inp_tokens,
            log_probs,
            eos_hyps_and_log_probs_scores,
            memory,
            scorer_memory,
            attn,
            prev_attn_peak,
            enc_states,
            enc_lens,
        ) = self.init_beam_search_data(enc_states, wav_len)

        for step in range(self.max_decode_steps):
            # terminate condition
            if self._check_full_beams(eos_hyps_and_log_probs_scores):
                break

            (
                alived_hyps,
                inp_tokens,
                log_probs,
                eos_hyps_and_log_probs_scores,
                memory,
                scorer_memory,
                attn,
                prev_attn_peak,
                scores,
            ) = self.search_step(
                alived_hyps,
                inp_tokens,
                log_probs,
                eos_hyps_and_log_probs_scores,
                memory,
                scorer_memory,
                attn,
                prev_attn_peak,
                enc_states,
                enc_lens,
                step,
            )

        finals_hyps_and_log_probs_scores = self._fill_alived_hyps_with_eos_token(
            alived_hyps, eos_hyps_and_log_probs_scores, scores,
        )

        (
            topk_hyps,
            topk_lengths,
            topk_scores,
            topk_log_probs,
        ) = self._get_topk_prediction(finals_hyps_and_log_probs_scores)

        if self.return_topk:
            return topk_hyps, topk_lengths, topk_scores, topk_log_probs
        else:
            # select the best hyps
            best_hyps = topk_hyps[:, 0, :]
            best_lens = topk_lengths[:, 0]
            best_scores = topk_scores[:, 0]
            best_log_probs = topk_log_probs[:, 0, :]

            # Convert best hypothesis to list
            hyps = undo_padding(best_hyps, best_lens)

            return hyps, best_lens, best_scores, best_log_probs

    def permute_mem(self, memory, index):
        """This method permutes the seq2seq model memory
        to synchronize the memory index with the current output.

        Arguments
        ---------
        memory : No limit
            The memory variable to be permuted.
        index : torch.Tensor
            The index of the previous path.

        Return
        ------
        The variable of the memory being permuted.

        """
        raise NotImplementedError


class S2SRNNBeamSearcher(S2SBeamSearcher):
    """
    This class implements the beam search decoding
    for AttentionalRNNDecoder (speechbrain/nnet/RNN.py).
    See also S2SBaseSearcher(), S2SBeamSearcher().

    Arguments
    ---------
    embedding : torch.nn.Module
        An embedding layer.
    decoder : torch.nn.Module
        Attentional RNN decoder.
    linear : torch.nn.Module
        A linear output layer.
    temperature : float
        Temperature factor applied to softmax. It changes the probability
        distribution, being softer when T>1 and sharper with T<1.
    **kwargs
        see S2SBeamSearcher, arguments are directly passed.

    Example
    -------
    >>> import speechbrain as sb
    >>> vocab_size = 5
    >>> emb = torch.nn.Embedding(vocab_size, 3)
    >>> dec = sb.nnet.RNN.AttentionalRNNDecoder(
    ...     "gru", "content", 3, 3, 1, enc_dim=7, input_size=3
    ... )
    >>> lin = sb.nnet.linear.Linear(n_neurons=vocab_size, input_size=3)
    >>> coverage_scorer = sb.decoders.scorer.CoverageScorer(vocab_size)
    >>> scorer = sb.decoders.scorer.ScorerBuilder(
    ...     full_scorers = [coverage_scorer],
    ...     partial_scorers = [],
    ...     weights= dict(coverage=1.5)
    ... )
    >>> searcher = S2SRNNBeamSearcher(
    ...     embedding=emb,
    ...     decoder=dec,
    ...     linear=lin,
    ...     bos_index=4,
    ...     eos_index=4,
    ...     min_decode_ratio=0,
    ...     max_decode_ratio=1,
    ...     beam_size=2,
    ...     scorer=scorer,
    ... )
    >>> batch_size = 2
    >>> enc = torch.rand([batch_size, 6, 7])
    >>> wav_len = torch.ones([batch_size])
    >>> hyps, _, _, _ = searcher(enc, wav_len)
    """

    def __init__(
        self, embedding, decoder, linear, temperature=1.0, **kwargs,
    ):
        super(S2SRNNBeamSearcher, self).__init__(**kwargs)
        self.emb = embedding
        self.dec = decoder
        self.fc = linear
        self.softmax = torch.nn.LogSoftmax(dim=-1)
        self.temperature = temperature

    def reset_mem(self, batch_size, device):
        """Needed to reset the memory during beamsearch."""
        hs = None
        self.dec.attn.reset()
        c = torch.zeros(batch_size, self.dec.attn_dim, device=device)
        return hs, c

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        with torch.no_grad():
            hs, c = memory
            e = self.emb(inp_tokens)
            dec_out, hs, c, w = self.dec.forward_step(
                e, hs, c, enc_states, enc_lens
            )
            log_probs = self.softmax(self.fc(dec_out) / self.temperature)
            # average attn weight of heads when attn_type is multiheadlocation
            if self.dec.attn_type == "multiheadlocation":
                w = torch.mean(w, dim=1)
        return log_probs, (hs, c), w

    def permute_mem(self, memory, index):
        """Memory permutation during beamsearch."""
        hs, c = memory

        # shape of hs: [num_layers, batch_size, n_neurons]
        if isinstance(hs, tuple):
            hs_0 = torch.index_select(hs[0], dim=1, index=index)
            hs_1 = torch.index_select(hs[1], dim=1, index=index)
            hs = (hs_0, hs_1)
        else:
            hs = torch.index_select(hs, dim=1, index=index)

        c = torch.index_select(c, dim=0, index=index)
        if self.dec.attn_type == "location":
            self.dec.attn.prev_attn = torch.index_select(
                self.dec.attn.prev_attn, dim=0, index=index
            )
        return (hs, c)


class S2STransformerBeamSearcher(S2SBeamSearcher):
    """This class implements the beam search decoding
    for Transformer.
    See also S2SBaseSearcher(), S2SBeamSearcher().
    Arguments
    ---------
    modules : list with the followings one:
        model : torch.nn.Module
            A Transformer model.
        seq_lin : torch.nn.Module
            A linear output layer.
    linear : torch.nn.Module
        A linear output layer.
    **kwargs
        Arguments to pass to S2SBeamSearcher
    Example
    -------
    >>> from speechbrain.nnet.linear import Linear
    >>> from speechbrain.lobes.models.transformer.TransformerASR import TransformerASR
    >>> from speechbrain.decoders import S2STransformerBeamSearcher
    >>> batch_size=8
    >>> n_channels=6
    >>> input_size=40
    >>> d_model=128
    >>> tgt_vocab=140
    >>> src = torch.rand([batch_size, n_channels, input_size])
    >>> tgt = torch.randint(0, tgt_vocab, [batch_size, n_channels])
    >>> net = TransformerASR(
    ...    tgt_vocab, input_size, d_model, 8, 1, 1, 1024, activation=torch.nn.GELU
    ... )
    >>> ctc_lin = Linear(input_shape=(1, 40, d_model), n_neurons=tgt_vocab)
    >>> lin = Linear(input_shape=(1, 40, d_model), n_neurons=tgt_vocab)
    >>> searcher = S2STransformerBeamSearcher(
    ...     modules=[net, lin],
    ...     bos_index=1,
    ...     eos_index=2,
    ...     min_decode_ratio=0.0,
    ...     max_decode_ratio=1.0,
    ...     using_eos_threshold=False,
    ...     beam_size=7,
    ...     temperature=1.15,
    ... )
    >>> enc, dec = net.forward(src, tgt)
    >>> hyps, _, _, _  = searcher(enc, torch.ones(batch_size))
    """

    def __init__(
        self, modules, temperature=1.0, **kwargs,
    ):
        super(S2STransformerBeamSearcher, self).__init__(**kwargs)

        self.model = modules[0]
        self.fc = modules[1]
        self.softmax = torch.nn.LogSoftmax(dim=-1)

        self.temperature = temperature

    def reset_mem(self, batch_size, device):
        """Needed to reset the memory during beamsearch."""
        return None

    def permute_mem(self, memory, index):
        """Memory permutation during beamsearch."""
        memory = torch.index_select(memory, dim=0, index=index)
        return memory

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        memory = _update_mem(inp_tokens, memory)
        pred, attn = self.model.decode(memory, enc_states, enc_lens)
        prob_dist = self.softmax(self.fc(pred) / self.temperature)
        return prob_dist[:, -1, :], memory, attn


class S2SWhisperGreedySearch(S2SGreedySearcher):
    """
    This class implements the greedy decoding
    for Whisper neural nets made by OpenAI in
    https://cdn.openai.com/papers/whisper.pdf.
    Arguments
    ---------
    model : HuggingFaceWhisper
        The Whisper model.
    language_token : int
        The language token to be used for the decoder input.
    bos_token : int
        The beginning of sentence token to be used for the decoder input.
    task_token : int
        The task token to be used for the decoder input.
    timestamp_token : int
        The timestamp token to be used for the decoder input.
    max_length : int
        The maximum decoding steps to perform.
        The Whisper model has a maximum length of 448.
    **kwargs
        see S2SBaseSearcher, arguments are directly passed.
    """

    def __init__(
        self,
        model,
        language_token=50259,
        bos_token=50258,
        task_token=50359,
        timestamp_token=50363,
        max_length=448,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model = model
        self.softmax = torch.nn.LogSoftmax(dim=-1)
        self.decoder_input_tokens = None
        self.language_token = language_token  # default language is english
        self.bos_token = bos_token  # always this value
        self.task_token = task_token  # default task is transcribe
        self.timestamp_token = timestamp_token  # default is notimestamp
        self.max_length = max_length - 3  # 3 tokens are added to the input

    def set_language_token(self, language_token):
        """set the language token to be used for the decoder input."""
        self.language_token = language_token

    def set_bos_token(self, bos_token):
        """set the bos token to be used for the decoder input."""
        self.bos_token = bos_token

    def set_task_token(self, task_token):
        """set the task token to be used for the decoder input."""
        self.task_token = task_token

    def set_timestamp_token(self, timestamp_token):
        """set the timestamp token to be used for the decoder input."""
        self.timestamp_token = timestamp_token
        # need to reset bos_index too as timestamp_token is the first
        # inp_token and need to be the first so that the first input gave
        # to the model is [bos, language, task, timestamp] (order matters).
        self.bos_index = self.timestamp_token

    def set_decoder_input_tokens(self, decoder_input_tokens):
        """decoder_input_tokens are the tokens used as input to the decoder.
        They are directly taken from the tokenizer.prefix_tokens attribute.
        decoder_input_tokens = [bos_token, language_token, task_token, timestamp_token]
        """
        self.set_bos_token(decoder_input_tokens[0])
        self.set_language_token(decoder_input_tokens[1])
        self.set_task_token(decoder_input_tokens[2])
        self.set_timestamp_token(decoder_input_tokens[3])

        # bos will be timestamp in our case.
        self.decoder_input_tokens = [
            self.bos_token,
            self.language_token,
            self.task_token,
        ]

    def reset_mem(self, batch_size, device):
        """This method set the first tokens to be decoder_input_tokens during search."""
        return torch.tensor([self.decoder_input_tokens] * batch_size).to(device)

    def permute_mem(self, memory, index):
        """Memory permutation during beamsearch."""
        memory = torch.index_select(memory, dim=0, index=index)
        return memory

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        memory = _update_mem(inp_tokens, memory)

        # WARNING: the max_decode_ratio need to be under 448 because
        #  of positinal encoding
        dec_out, attn = self.model.forward_decoder(enc_states, memory)
        log_probs = self.softmax(dec_out[:, -1])

        return log_probs, memory, attn

    def change_max_decoding_length(self, min_decode_steps, max_decode_steps):
        """set the minimum/maximum length the decoder can take."""
        return (
            int(self.min_decode_ratio * self.max_length),
            int(self.max_decode_ratio * self.max_length),
        )


class S2STransformerGreedySearch(S2SGreedySearcher):
    """This class implements the greedy decoding
    for Transformer.

    Arguments
    ---------
    modules : list with the followings one:
        model : torch.nn.Module
            A TransformerASR model.
        seq_lin : torch.nn.Module
            A linear output layer for the seq2seq model.
    temperature : float
        Temperature to use during decoding.
    **kwargs
        Arguments to pass to S2SGreedySearcher
    """

    def __init__(
        self, modules, temperature=1.0, **kwargs,
    ):
        super(S2SGreedySearcher, self).__init__(**kwargs)

        self.model = modules[0]
        self.fc = modules[1]
        self.softmax = torch.nn.LogSoftmax(dim=-1)

        self.temperature = temperature

    def reset_mem(self, batch_size, device):
        """Needed to reset the memory during greedy search."""
        return None

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented greedy searcher."""
        memory = _update_mem(inp_tokens, memory)
        pred, attn = self.model.decode(memory, enc_states, enc_lens)
        prob_dist = self.softmax(self.fc(pred) / self.temperature)
        return prob_dist[:, -1, :], memory, attn


class S2SWhisperBeamSearch(S2SBeamSearcher):
    """This class implements the beam search decoding
    for Whisper neural nets made by OpenAI in
    https://cdn.openai.com/papers/whisper.pdf.
    Arguments
    ---------
    module : list with the followings one:
        model : torch.nn.Module
            A whisper model. It should have a decode() method.
        ctc_lin : torch.nn.Module (optional)
            A linear output layer for CTC.
    language_token : int
        The token to use for language.
    bos_token : int
        The token to use for beginning of sentence.
    task_token : int
        The token to use for task.
    timestamp_token : int
        The token to use for timestamp.
    max_length : int
        The maximum decoding steps to perform.
        The Whisper model has a maximum length of 448.
    **kwargs
        Arguments to pass to S2SBeamSearcher
    """

    def __init__(
        self,
        module,
        temperature=1.0,
        language_token=50259,
        bos_token=50258,
        task_token=50359,
        timestamp_token=50363,
        max_length=448,
        **kwargs,
    ):
        super(S2SWhisperBeamSearch, self).__init__(**kwargs)

        self.model = module[0]

        self.softmax = torch.nn.LogSoftmax(dim=-1)

        self.temperature = temperature

        self.decoder_input_tokens = None
        self.language_token = language_token  # default language is english
        self.bos_token = bos_token  # always this value
        self.task_token = task_token  # default task is transcribe
        self.timestamp_token = timestamp_token  # default is notimestamp

        self.max_length = max_length - 3  # -3 for [bos, language, task]

    def set_language_token(self, language_token):
        """set the language token to use for the decoder input."""
        self.language_token = language_token

    def set_bos_token(self, bos_token):
        """set the bos token to use for the decoder input."""
        self.bos_token = bos_token

    def set_task_token(self, task_token):
        """set the task token to use for the decoder input."""
        self.task_token = task_token

    def set_timestamp_token(self, timestamp_token):
        """set the timestamp token to use for the decoder input."""
        self.timestamp_token = timestamp_token
        # need to reset bos_index too as timestamp_token is the first
        # inp_token and need to be the first so that the first input gave
        # to the model is [bos, language, task, timestamp] (order matters).
        self.bos_index = self.timestamp_token

    def change_max_decoding_length(self, min_decode_steps, max_decode_steps):
        """set the minimum/maximum length the decoder can take."""
        return (
            int(self.min_decode_ratio * self.max_length),
            int(self.max_decode_ratio * self.max_length),
        )

    def set_decoder_input_tokens(self, decoder_input_tokens):
        """decoder_input_tokens are the tokens used as input to the decoder.
        They are directly taken from the tokenizer.prefix_tokens attribute.
        decoder_input_tokens = [bos_token, language_token, task_token, timestamp_token]
        """
        self.set_bos_token(decoder_input_tokens[0])
        self.set_language_token(decoder_input_tokens[1])
        self.set_task_token(decoder_input_tokens[2])
        self.set_timestamp_token(decoder_input_tokens[3])

        # bos will be timestamp in our case.
        self.decoder_input_tokens = [
            self.bos_token,
            self.language_token,
            self.task_token,
        ]

    def reset_mem(self, batch_size, device):
        """This method set the first tokens to be decoder_input_tokens during search."""
        return torch.tensor([self.decoder_input_tokens] * batch_size).to(device)

    def permute_mem(self, memory, index):
        """Permutes the memory."""
        memory = torch.index_select(memory, dim=0, index=index)
        return memory

    def set_n_out(self):
        """set the number of output tokens."""
        return self.model.model.decoder.embed_tokens.weight.shape[0]

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        memory = _update_mem(inp_tokens, memory)
        dec_out, attn, = self.model.forward_decoder(enc_states, memory)
        log_probs = self.softmax(dec_out[:, -1] / self.temperature)
        return log_probs, memory, attn


class S2SHFTextBasedBeamSearcher(S2STransformerBeamSearcher):
    """This class implements the beam search decoding
    for the text-based HF seq2seq models, such as mBART or NLLB.
    It is NOT significantly different from S2STransformerBeamSearcher.
    This is why it inherits S2STransformerBeamSearcher.
    The main difference might arise when one wishes to use directly
    the lm_head of the text-based HF model rather than making a new
    projection layer (self.fc = None).

    Arguments
    ---------
    modules : list with the followings one:
        model : torch.nn.Module
            A Transformer model.
        seq_lin : torch.nn.Module
            A linear output layer.
            Normally set to None for this usecase.
    vocab_size : int
        The dimension of the lm_head.
    **kwargs
        Arguments to pass to S2SBeamSearcher
    """

    def __init__(self, modules, vocab_size, **kwargs):
        super(S2SHFTextBasedBeamSearcher, self).__init__(modules, **kwargs)
        self.vocab_size = vocab_size

    def forward_step(self, inp_tokens, memory, enc_states, enc_lens):
        """Performs a step in the implemented beamsearcher."""
        memory = _update_mem(inp_tokens, memory)
        pred, attn = self.model.decode(memory, enc_states, enc_lens)
        if self.fc is not None:
            pred = self.fc(pred)
        prob_dist = self.softmax(pred / self.temperature)
        return prob_dist[:, -1, :], memory, attn

    def set_n_out(self):
        """set the number of output tokens."""
        return self.vocab_size
